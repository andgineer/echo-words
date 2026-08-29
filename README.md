# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/andgineer/echo-words/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                             |    Stmts |     Miss |   Cover |   Missing |
|--------------------------------- | -------: | -------: | ------: | --------: |
| src/echo\_words/\_\_about\_\_.py |        1 |        0 |    100% |           |
| src/echo\_words/anki.py          |      469 |       28 |     94% |125, 136, 221, 228, 235, 251, 367, 408, 559, 595-597, 627, 647, 670, 689, 712, 717, 760, 828, 885-886, 892-893, 897-900 |
| src/echo\_words/api.py           |      283 |       25 |     91% |73, 118, 135, 145, 185, 277-279, 287-289, 298-300, 309-310, 316-319, 374, 378-379, 397-398 |
| src/echo\_words/api\_backend.py  |       17 |        0 |    100% |           |
| src/echo\_words/audio.py         |      228 |       26 |     89% |111, 113-115, 154, 158, 165-168, 178-179, 226-227, 252, 258, 273, 277-278, 361, 406-410, 416 |
| src/echo\_words/backend.py       |      186 |        4 |     98% |169, 279-282, 303 |
| src/echo\_words/broker.py        |       28 |        0 |    100% |           |
| src/echo\_words/card.py          |      253 |       19 |     92% |113-114, 167-168, 226-235, 240, 255, 261, 287, 298, 310, 320, 363, 447, 453, 477 |
| src/echo\_words/config.py        |       41 |        0 |    100% |           |
| src/echo\_words/events.py        |       34 |        0 |    100% |           |
| src/echo\_words/history.py       |      102 |        1 |     99% |       114 |
| src/echo\_words/i18n.py          |       23 |        0 |    100% |           |
| src/echo\_words/languages.py     |      118 |        1 |     99% |        72 |
| src/echo\_words/llm\_backend.py  |       38 |        0 |    100% |           |
| src/echo\_words/main.py          |       25 |        0 |    100% |           |
| src/echo\_words/pipeline.py      |      571 |       37 |     94% |180, 310, 339, 368, 389, 412, 444, 453-454, 494, 551, 553, 588-589, 615, 647, 662-665, 857, 865, 874, 899, 902, 920-923, 927, 931, 984, 1020, 1067-1070 |
| src/echo\_words/prompt.py        |       43 |        0 |    100% |           |
| src/echo\_words/sanitizer.py     |       25 |        1 |     96% |        37 |
| src/echo\_words/segments.py      |       66 |        8 |     88% |29, 41, 63, 65, 69, 72, 90, 94 |
| **TOTAL**                        | **2551** |  **150** | **94%** |           |


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