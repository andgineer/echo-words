# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/andgineer/echo-words/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                             |    Stmts |     Miss |   Cover |   Missing |
|--------------------------------- | -------: | -------: | ------: | --------: |
| src/echo\_words/\_\_about\_\_.py |        1 |        0 |    100% |           |
| src/echo\_words/anki.py          |      469 |       28 |     94% |125, 136, 221, 228, 235, 251, 367, 408, 559, 595-597, 627, 647, 670, 689, 712, 717, 760, 828, 885-886, 892-893, 897-900 |
| src/echo\_words/api.py           |      288 |       22 |     92% |74, 119, 136, 146, 188, 303-305, 314-316, 325-326, 332-335, 390, 394-395, 413-414 |
| src/echo\_words/api\_backend.py  |       17 |        0 |    100% |           |
| src/echo\_words/audio.py         |      228 |       26 |     89% |111, 113-115, 154, 158, 165-168, 178-179, 226-227, 252, 258, 273, 277-278, 361, 406-410, 416 |
| src/echo\_words/backend.py       |      216 |        4 |     98% |228, 344-347, 368 |
| src/echo\_words/broker.py        |       28 |        0 |    100% |           |
| src/echo\_words/card.py          |      250 |       18 |     93% |120-121, 173-174, 231-240, 245, 261, 267, 295, 307, 320, 330, 385, 476, 500 |
| src/echo\_words/config.py        |       41 |        0 |    100% |           |
| src/echo\_words/events.py        |       34 |        0 |    100% |           |
| src/echo\_words/history.py       |      105 |        1 |     99% |       126 |
| src/echo\_words/i18n.py          |       23 |        0 |    100% |           |
| src/echo\_words/languages.py     |      144 |        1 |     99% |        72 |
| src/echo\_words/lexicon.py       |       81 |        1 |     99% |       169 |
| src/echo\_words/llm\_backend.py  |       38 |        0 |    100% |           |
| src/echo\_words/main.py          |       25 |        0 |    100% |           |
| src/echo\_words/pipeline.py      |      669 |       38 |     94% |205, 333, 362, 383, 406, 438, 448-449, 504, 594, 674, 692, 699-700, 726, 758, 773-776, 971, 979, 988, 1013, 1016, 1034-1037, 1041, 1045, 1137, 1228, 1240, 1281-1284 |
| src/echo\_words/prompt.py        |       72 |        2 |     97% |   299-300 |
| src/echo\_words/sanitizer.py     |       25 |        1 |     96% |        37 |
| src/echo\_words/segments.py      |      103 |        9 |     91% |40, 52, 74, 76, 80, 83, 101, 105, 173 |
| **TOTAL**                        | **2857** |  **151** | **95%** |           |


## Setup coverage badge

Below are examples of the badges you can use in your main branch `README` file.

### Direct image

[![Coverage badge](https://raw.githubusercontent.com/andgineer/echo-words/python-coverage-comment-action-data/badge.svg)](https://htmlpreview.github.io/?https://github.com/andgineer/echo-words/blob/python-coverage-comment-action-data/htmlcov/index.html)

This is the one to use if your repository is private or if you don't want to customize anything.

### [Shields.io](https://shields.io) Json Endpoint

[![Coverage badge](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/andgineer/echo-words/python-coverage-comment-action-data/endpoint.json)](https://htmlpreview.github.io/?https://github.com/andgineer/echo-words/blob/python-coverage-comment-action-data/htmlcov/index.html)

Using this one will allow you to [customize](https://shields.io/endpoint) the look of your badge.
It won't work with private repositories. It won't be refreshed more than once per five minutes.

### [Shields.io](https://shields.io) Dynamic Badge

[![Coverage badge](https://img.shields.io/badge/dynamic/json?color=brightgreen&label=coverage&query=%24.message&url=https%3A%2F%2Fraw.githubusercontent.com%2Fandgineer%2Fecho-words%2Fpython-coverage-comment-action-data%2Fendpoint.json)](https://htmlpreview.github.io/?https://github.com/andgineer/echo-words/blob/python-coverage-comment-action-data/htmlcov/index.html)

This one will always be the same color. It won't work for private repos. I'm not even sure why we included it.

## What is that?

This branch is part of the
[python-coverage-comment-action](https://github.com/marketplace/actions/python-coverage-comment)
GitHub Action. All the files in this branch are automatically generated and may be
overwritten at any moment.