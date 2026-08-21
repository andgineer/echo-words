"""Headless Anki spike — the M5 sync spike from spec/decision-spaced-repetition.md.

Proves that a server can maintain an Anki collection and push cards to the
user's devices with no Anki application running anywhere: no Qt, no GUI, no
AnkiConnect, no desktop app on the laptop.

Outside the package and outside CI: it touches the real network (the
``ankiweb`` phase) and starts a real sync server (the ``selfhosted`` phase).

Run:
    uv run --no-project --python 3.12 --with anki==26.8.1 \\
        python experiments/anki_headless_spike.py local
    uv run --no-project --python 3.12 --with anki==26.8.1 \\
        python experiments/anki_headless_spike.py selfhosted
    ECHOWORDS_ANKIWEB_USER=... ECHOWORDS_ANKIWEB_PASSWORD=... \\
    uv run --no-project --python 3.12 --with anki==26.8.1 \\
        python experiments/anki_headless_spike.py ankiweb [--bootstrap] [--add-note] [--verify]

``--cleanup`` removes the spike's deck and notes from the account again; the
note type stays behind, which is why it carries a name of its own. The only
automatic full transfer is the first-run download; a full upload is refused,
so the spike can never clobber the user's other decks.
"""

import argparse
import contextlib
import hashlib
import math
import os
import resource
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

from anki.collection import Collection
from anki.sync import SyncAuth
from anki.sync_pb2 import SyncCollectionResponse, SyncStatusResponse

# Never the app's own "EchoWords": cleanup cannot remove a note type, so a shared name
# would leave the app facing a leftover it reads as misconfigured.
NOTE_TYPE = "EchoWordsSpike"
FIELDS = ["Word", "IPA", "Translations", "Meanings", "Audio"]
DECK = "echo-words spike"
WORD = "заглушка"
SPIKE_TAG = "echo-words-spike"

REQUIRED = {v: k for k, v in SyncCollectionResponse.ChangesRequired.items()}
STATUS = {v: k for k, v in SyncStatusResponse.Required.items()}


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def rss_mb() -> float:
    """Peak RSS of this process. ru_maxrss is bytes on macOS, kilobytes on Linux."""
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak / 1024**2 if sys.platform == "darwin" else peak / 1024


def dir_size_mb(path: Path) -> float:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file()) / 1024**2


def make_wav(path: Path, seconds: float = 0.4, freq: int = 440) -> Path:
    rate = 22050
    frames = b"".join(
        struct.pack("<h", int(12000 * math.sin(2 * math.pi * freq * i / rate)))
        for i in range(int(rate * seconds))
    )
    with wave.open(str(path), "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(rate)
        fh.writeframes(frames)
    return path


def ensure_note_type(col: Collection) -> dict:
    existing = col.models.by_name(NOTE_TYPE)
    if existing:
        return existing
    mm = col.models
    model = mm.new(NOTE_TYPE)
    for name in FIELDS:
        mm.add_field(model, mm.new_field(name))
    recognition = mm.new_template("Recognition")
    recognition["qfmt"] = "{{Word}} {{Audio}}<br>{{IPA}}"
    recognition["afmt"] = "{{FrontSide}}<hr id=answer>{{Meanings}}"
    mm.add_template(model, recognition)
    recall = mm.new_template("Recall")
    recall["qfmt"] = "{{Translations}}"
    recall["afmt"] = "{{FrontSide}}<hr id=answer>{{Word}} {{Audio}}<br>{{IPA}}"
    mm.add_template(model, recall)
    mm.add(model)
    return mm.by_name(NOTE_TYPE)


def add_spike_note(col: Collection, word: str, audio: Path) -> tuple[int, str]:
    """Add one note the way M5 describes it: media file first, [sound:] in the field."""
    model = ensure_note_type(col)
    deck_id = col.decks.id(DECK)
    existing = col.find_notes(f'deck:"{DECK}" note:{NOTE_TYPE} "Word:{word}"')
    if existing:
        note = col.get_note(existing[0])
        log(f"  note already present ({note.id}) — dedup hit, nothing added")
        return note.id, note["Audio"].removeprefix("[sound:").removesuffix("]")
    slug = "".join(c if c.isalnum() else "-" for c in word.lower()).strip("-")
    digest = hashlib.sha1(word.encode()).hexdigest()[:8]
    staged = audio.with_name(f"echo-words-{slug}-{digest}{audio.suffix}")
    shutil.copyfile(audio, staged)
    media_name = col.media.add_file(str(staged))
    note = col.new_note(model)
    note["Word"] = word
    note["IPA"] = "[zɐˈɡluʂkə]"
    note["Translations"] = "<b>placeholder</b><br>a ___ card from the spike"
    note["Meanings"] = "<ol><li>placeholder, stub</li></ol>"
    note["Audio"] = f"[sound:{media_name}]"
    note.tags = [SPIKE_TAG]
    col.add_note(note, deck_id)
    return note.id, media_name


def find_spike(col: Collection) -> tuple[list[int], list[str]]:
    ids = col.find_notes(f'note:{NOTE_TYPE} "Word:{WORD}"')
    media = [n for n in os.listdir(col.media.dir()) if n.startswith("echo-words-")]
    return list(ids), sorted(media)


def open_fresh(root: Path, name: str) -> Collection:
    path = root / name / "collection.anki2"
    path.parent.mkdir(parents=True, exist_ok=True)
    return Collection(str(path))


def report_sync(out: SyncCollectionResponse) -> str:
    return (
        f"required={REQUIRED[out.required]} host_number={out.host_number} "
        f"new_endpoint={out.new_endpoint!r} "
        f"server_media_usn={out.server_media_usn} message={out.server_message!r}"
    )


def follow_endpoint(auth: SyncAuth, new_endpoint: str) -> SyncAuth:
    """AnkiWeb answers on a shard; the full-sync request must go there, not to the
    login endpoint, or its response arrives without the anki-original-size header."""
    if not new_endpoint or new_endpoint == auth.endpoint:
        return auth
    log(f"  following new endpoint {new_endpoint}")
    return SyncAuth(hkey=auth.hkey, endpoint=new_endpoint)


def phase_local(root: Path) -> None:
    log("PHASE local — collection + note + media, fully offline, no Anki app")
    t0 = time.time()
    col = open_fresh(root, "local")
    log(f"  Collection opened in {time.time() - t0:.2f}s at {col.path}")
    audio = make_wav(root / "tone.wav")
    t1 = time.time()
    note_id, media_name = add_spike_note(col, WORD, audio)
    log(f"  note {note_id} added in {time.time() - t1:.3f}s, media {media_name!r}")
    cards = col.card_count_for_notes([note_id]) if hasattr(col, "card_count_for_notes") else None
    ids, media = find_spike(col)
    log(f"  find_notes -> {ids}, media dir -> {media}, cards={cards or len(col.find_cards('deck:*'))}")
    dupes = col.find_notes(f'deck:"{DECK}" note:{NOTE_TYPE} "Word:{WORD}"')
    log(f"  deck-scoped dedup query -> {len(dupes)} hit(s)")
    col.close()
    base = Path(col.path).parent
    log(f"  collection {Path(col.path).stat().st_size / 1024:.0f} KB, dir {dir_size_mb(base):.2f} MB")
    log(f"  peak RSS after local phase: {rss_mb():.0f} MB")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextlib.contextmanager
def sync_server(base: Path, user: str, password: str):
    """Anki's own sync server (the documented AnkiWeb fallback), headless."""
    port = free_port()
    base.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        "SYNC_BASE": str(base),
        "SYNC_HOST": "127.0.0.1",
        "SYNC_PORT": str(port),
        "SYNC_USER1": f"{user}:{password}",
        "RUST_LOG": "anki=warn",
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "anki.syncserver"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    endpoint = f"http://127.0.0.1:{port}/"
    deadline = time.time() + 30
    while time.time() < deadline:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                break
        if proc.poll() is not None:
            raise RuntimeError(f"sync server died: {proc.stdout.read() if proc.stdout else ''}")
        time.sleep(0.2)
    else:
        proc.kill()
        raise RuntimeError("sync server did not start")
    try:
        yield endpoint
    finally:
        proc.terminate()
        with contextlib.suppress(subprocess.TimeoutExpired):
            proc.wait(timeout=10)


def sync_up(col: Collection, auth: SyncAuth, allow_full_upload: bool) -> SyncAuth:
    out = col.sync_collection(auth, True)
    log(f"  sync_collection -> {report_sync(out)}")
    auth = follow_endpoint(auth, out.new_endpoint)
    if out.required == SyncCollectionResponse.FULL_UPLOAD:
        if not allow_full_upload:
            raise RuntimeError("server asked for FULL_UPLOAD — refusing (would clobber remote)")
        col.close_for_full_sync()
        col.full_upload_or_download(auth=auth, server_usn=out.server_media_usn, upload=True)
        col.reopen(after_full_sync=True)
        log("  full upload done")
    elif out.required == SyncCollectionResponse.FULL_DOWNLOAD:
        raise RuntimeError("server asked for FULL_DOWNLOAD while uploading — diverged")
    elif out.required == SyncCollectionResponse.FULL_SYNC:
        raise RuntimeError("server demands a one-way full sync — local changes were NOT pushed")
    col.sync_media(auth)
    wait_media(col)
    return auth


def wait_media(col: Collection, timeout: float = 900) -> None:
    deadline = time.time() + timeout
    last = 0.0
    while time.time() < deadline:
        status = col.media_sync_status()
        if status.active and time.time() - last > 15:
            last = time.time()
            log(f"  media sync in progress: {status.progress.checked} checked")
        if not status.active:
            log(f"  media sync finished: {status.progress.added} added, {status.progress.removed} removed, {status.progress.checked} checked")
            return
        time.sleep(0.5)
    raise RuntimeError("media sync did not finish")


def bootstrap_download(col: Collection, auth: SyncAuth) -> SyncAuth:
    """The only automatic full transfer M5 allows: first-run download."""
    out = col.sync_collection(auth, True)
    log(f"  sync_collection -> {report_sync(out)}")
    auth = follow_endpoint(auth, out.new_endpoint)
    if out.required in (
        SyncCollectionResponse.FULL_DOWNLOAD,
        SyncCollectionResponse.FULL_SYNC,
    ):
        t0 = time.time()
        col.close_for_full_sync()
        col.full_upload_or_download(auth=auth, server_usn=out.server_media_usn, upload=False)
        col.reopen(after_full_sync=True)
        log(f"  full DOWNLOAD done in {time.time() - t0:.1f}s")
    elif out.required == SyncCollectionResponse.FULL_UPLOAD:
        raise RuntimeError("fresh collection triggered FULL_UPLOAD — refusing")
    return auth


def phase_selfhosted(root: Path) -> None:
    log("PHASE selfhosted — full sync round-trip through Anki's own sync server")
    base = root / "syncserver"
    with sync_server(base, "spike", "spike-pass") as endpoint:
        log(f"  sync server up at {endpoint} (no GUI, no Anki app)")
        server = open_fresh(root, "server-side")
        auth = server.sync_login("spike", "spike-pass", endpoint)
        log(f"  sync_login ok, hkey={auth.hkey[:8]}… endpoint={auth.endpoint}")
        log(f"  sync_status -> {STATUS[server.sync_status(auth).required]}")
        audio = make_wav(root / "tone.wav")
        note_id, media_name = add_spike_note(server, WORD, audio)
        log(f"  server-side note {note_id} with media {media_name!r}")
        auth = sync_up(server, auth, allow_full_upload=True)
        server.close()

        log("  --- now a *device*: a second fresh collection pulls from the same server ---")
        device = open_fresh(root, "device-side")
        dev_auth = device.sync_login("spike", "spike-pass", endpoint)
        dev_auth = bootstrap_download(device, dev_auth)
        device.sync_media(dev_auth)
        wait_media(device)
        ids, media = find_spike(device)
        note = device.get_note(ids[0]) if ids else None
        log(f"  device sees notes={ids} media={media}")
        log(f"  device deck list: {[d.name for d in device.decks.all_names_and_ids()]}")
        if note:
            log(f"  device note fields: Word={note['Word']!r} Audio={note['Audio']!r}")
        media_ok = bool(media) and (Path(device.media.dir()) / media[0]).stat().st_size > 0
        device.close()
        verdict = "PASS" if note and media_ok else "FAIL"
        log(f"  round-trip verdict: {verdict} (note carried across, media bytes present={media_ok})")
    log(f"  peak RSS after selfhosted phase: {rss_mb():.0f} MB")


def phase_cleanup(col: Collection, auth: SyncAuth) -> None:
    """Remove everything the spike put into the account, then push the removal."""
    ids = col.find_notes(f"tag:{SPIKE_TAG}")
    if ids:
        col.remove_notes(list(ids))
        log(f"  removed {len(ids)} spike note(s)")
    deck_id = col.decks.id_for_name(DECK)
    if deck_id is not None:
        col.decks.remove([deck_id])
        log(f"  removed deck {DECK!r}")
    # The note type is left behind: removing one is a schema change, after which
    # AnkiWeb demands a one-way full sync — which this spike refuses.
    sync_up(col, auth, allow_full_upload=False)


def phase_ankiweb(
    root: Path, bootstrap: bool, add_note: bool, verify: bool, cleanup: bool
) -> None:
    user = os.environ.get("ECHOWORDS_ANKIWEB_USER")
    password = os.environ.get("ECHOWORDS_ANKIWEB_PASSWORD")
    endpoint = os.environ.get("ECHOWORDS_SYNC_ENDPOINT") or None
    if not user or not password:
        sys.exit("set ECHOWORDS_ANKIWEB_USER and ECHOWORDS_ANKIWEB_PASSWORD")
    log(f"PHASE ankiweb — real AnkiWeb as {user}, endpoint={endpoint or 'default'}")
    col = open_fresh(root, "ankiweb")
    t0 = time.time()
    auth = col.sync_login(user, password, endpoint)
    log(f"  sync_login ok in {time.time() - t0:.1f}s, hkey={auth.hkey[:6]}… endpoint={auth.endpoint}")
    status = col.sync_status(auth)
    log(f"  sync_status -> {STATUS[status.required]} new_endpoint={status.new_endpoint!r}")
    auth = follow_endpoint(auth, status.new_endpoint)
    if not bootstrap:
        col.close()
        log("  read-only probe done (pass --bootstrap to download the collection)")
        return
    auth = bootstrap_download(col, auth)
    decks = [d.name for d in col.decks.all_names_and_ids()]
    log(f"  downloaded: {col.note_count()} notes, {col.card_count()} cards, decks={decks}")
    log(f"  collection file {Path(col.path).stat().st_size / 1024**2:.1f} MB")
    log(f"  peak RSS with the real collection open: {rss_mb():.0f} MB")
    if cleanup:
        phase_cleanup(col, auth)
        col.close()
        log("  account cleaned of everything the spike added")
        return
    if not add_note:
        col.close()
        log("  no write performed (pass --add-note to push a card to AnkiWeb)")
        return
    audio = make_wav(root / "tone.wav")
    note_id, media_name = add_spike_note(col, WORD, audio)
    log(f"  added note {note_id} in deck {DECK!r} with media {media_name!r}")
    t1 = time.time()
    auth = sync_up(col, auth, allow_full_upload=False)
    log(f"  pushed to AnkiWeb in {time.time() - t1:.1f}s")
    col.close()
    if not verify:
        log("  check AnkiDroid / ankiweb.net for the card")
        return
    log("  --- verifying from a second fresh collection (stands in for the phone) ---")
    other = open_fresh(root, "ankiweb-verify")
    other_auth = other.sync_login(user, password, endpoint)
    other_auth = bootstrap_download(other, other_auth)
    other.sync_media(other_auth)
    wait_media(other)
    ids, media = find_spike(other)
    log(f"  second client sees notes={ids} media={media}")
    other.close()
    log(f"  AnkiWeb round-trip verdict: {'PASS' if ids and media else 'FAIL'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["local", "selfhosted", "ankiweb"])
    parser.add_argument("--bootstrap", action="store_true", help="ankiweb: full-download first")
    parser.add_argument("--add-note", action="store_true", help="ankiweb: push a real card")
    parser.add_argument("--verify", action="store_true", help="ankiweb: re-download and check")
    parser.add_argument(
        "--cleanup", action="store_true", help="ankiweb: delete what the spike added, then sync"
    )
    parser.add_argument("--keep", metavar="DIR", help="work in DIR instead of a temp dir")
    args = parser.parse_args()

    root = Path(args.keep) if args.keep else Path(tempfile.mkdtemp(prefix="anki-spike-"))
    root.mkdir(parents=True, exist_ok=True)
    log(f"work dir {root}")
    from anki.buildinfo import version

    log(f"anki pylib {version}, python {sys.version.split()[0]}, {sys.platform}")
    try:
        if args.phase == "local":
            phase_local(root)
        elif args.phase == "selfhosted":
            phase_selfhosted(root)
        else:
            phase_ankiweb(
                root, args.bootstrap or args.cleanup, args.add_note, args.verify, args.cleanup
            )
    finally:
        if not args.keep:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    main()
