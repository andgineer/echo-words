// Every sense of one word is chipped under that same word, so the label repeats down
// the row and the meaning underneath is the only thing telling them apart. On a rail
// of senses the meaning is the chip; the parts of a phrase keep their own wording.
function chipsAreSenses(entry) {
  return entry.segment_kind === "senses";
}

export function visibleSegments(entry) {
  const segments = entry.segments ?? [];
  if (!chipsAreSenses(entry) || entry.card_status !== "added") return segments;
  return segments.filter((_, index) => index !== entry.carded_sense);
}

export function chipLabel(entry, segment) {
  return chipsAreSenses(entry) && segment.reason ? segment.reason : segment.label;
}

export function chipNote(entry, segment) {
  return chipsAreSenses(entry) && segment.reason ? "" : segment.reason || "";
}
