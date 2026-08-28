# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/andgineer/echo-words/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                             |    Stmts |     Miss |   Cover |   Missing |
|--------------------------------- | -------: | -------: | ------: | --------: |
| src/echo\_words/\_\_about\_\_.py |        1 |        0 |    100% |           |
| src/echo\_words/anki.py          |      411 |       27 |     93% |130, 134, 212, 219, 226, 277, 428, 464-466, 496, 516, 552, 588, 607, 630, 635, 640, 684, 741-742, 748-749, 753-756 |
| src/echo\_words/api.py           |      274 |       22 |     92% |73, 118, 135, 145, 185, 277-279, 288-290, 299-300, 306-309, 364, 368-369, 387-388 |
| src/echo\_words/api\_backend.py  |       17 |        0 |    100% |           |
| src/echo\_words/audio.py         |      201 |       26 |     87% |101, 103-105, 144, 148, 152-153, 164-167, 194-195, 220, 226, 241, 245-246, 307, 352-356, 362 |
| src/echo\_words/backend.py       |      186 |        4 |     98% |169, 279-282, 303 |
| src/echo\_words/broker.py        |       28 |        0 |    100% |           |
| src/echo\_words/card.py          |      249 |       19 |     92% |105-106, 158-159, 216-225, 230, 245, 251, 277, 288, 300, 310, 353, 437, 443, 467 |
| src/echo\_words/config.py        |       41 |        0 |    100% |           |
| src/echo\_words/events.py        |       34 |        0 |    100% |           |
| src/echo\_words/history.py       |      101 |        1 |     99% |       112 |
| src/echo\_words/i18n.py          |       23 |        0 |    100% |           |
| src/echo\_words/languages.py     |      118 |        1 |     99% |        72 |
| src/echo\_words/llm\_backend.py  |       38 |        0 |    100% |           |
| src/echo\_words/main.py          |       22 |        0 |    100% |           |
| src/echo\_words/pipeline.py      |      550 |       38 |     93% |177, 305, 337, 358, 381, 413, 422-423, 462, 515-518, 550-551, 577, 609, 624-627, 799, 807, 816, 841, 844, 862-865, 869, 873, 925, 961, 1003-1006 |
| src/echo\_words/prompt.py        |       39 |        0 |    100% |           |
| src/echo\_words/sanitizer.py     |       25 |        1 |     96% |        37 |
| src/echo\_words/segments.py      |       66 |        8 |     88% |29, 41, 63, 65, 69, 72, 90, 94 |
| **TOTAL**                        | **2424** |  **147** | **94%** |           |


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