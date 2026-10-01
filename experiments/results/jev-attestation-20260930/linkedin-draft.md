I prepared a Jev test with fake words. An Austrian cafe was already serving one of them.

TypeSafe released Jev in September. It returns decisions and probabilities instead of writing text. I wanted to try it on a small job in echo-words, my language-learning app: checking whether people actually use a word before making an Anki card.

I asked a coding agent to build a comparison with my existing LLM checker. A separate agent checked the test words against sources.

Before we called either model, that reviewer found real uses for three of six supposedly invented words. "Fahrradsuppe" was on a cafe's menu. "Bookshelfy" appeared in an interior-design article from 2016.

We kept the words and corrected how we would score them.

Then we tested 44 inputs in English, German and Serbian, once with each approach. Jev's median response took 0.29 seconds. The current LLM pool took 0.92 seconds. Jev was faster in 43 of the 44 pairs.

But at our chosen cutoff, Jev rejected four of the 35 words with confirmed usage. The LLM pool rejected two. Both rejected the cafe's soup.

The separate agent then reviewed every pair of answers. Agreement between models was not enough; we had just found a menu that disagreed with both.

This was a small experiment, not enough to choose a production replacement. But the agents made it practical to try a new model, check the evidence and inspect the mistakes in a working project.

Jev stays in my experiments for now. The soup stays in the test set.
