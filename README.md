# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/andgineer/echo-words/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                             |    Stmts |     Miss |   Cover |   Missing |
|--------------------------------- | -------: | -------: | ------: | --------: |
| src/echo\_words/\_\_about\_\_.py |        1 |        0 |    100% |           |
| src/echo\_words/anki.py          |      415 |       26 |     94% |127, 134, 141, 193, 352, 388-390, 420, 440, 476, 512, 541, 549, 576, 581, 586, 617, 700-701, 707-708, 712-715 |
| src/echo\_words/api.py           |      258 |       23 |     91% |67, 112, 129, 139, 179, 257-259, 267-269, 277-278, 282-286, 341, 345-346, 364-365 |
| src/echo\_words/api\_backend.py  |       17 |        0 |    100% |           |
| src/echo\_words/audio.py         |      191 |       26 |     86% |85, 87-89, 128, 132, 136-137, 148-151, 178-179, 204, 210, 225, 229-230, 275, 320-324, 330 |
| src/echo\_words/backend.py       |      155 |        3 |     98% |223-226, 247 |
| src/echo\_words/broker.py        |       28 |        0 |    100% |           |
| src/echo\_words/card.py          |       72 |        2 |     97% |  117, 131 |
| src/echo\_words/config.py        |       40 |        0 |    100% |           |
| src/echo\_words/events.py        |       34 |        0 |    100% |           |
| src/echo\_words/history.py       |       85 |        1 |     99% |        93 |
| src/echo\_words/languages.py     |       89 |        1 |     99% |        72 |
| src/echo\_words/llm\_backend.py  |       38 |        0 |    100% |           |
| src/echo\_words/main.py          |       11 |        0 |    100% |           |
| src/echo\_words/pipeline.py      |      441 |       36 |     92% |157, 266, 289, 310, 331, 355, 364-365, 385, 428-429, 443-444, 470, 487-494, 525, 622, 629, 638, 663, 666, 681-684, 688, 692, 734, 775 |
| src/echo\_words/prompt.py        |       21 |        0 |    100% |           |
| src/echo\_words/sanitizer.py     |       24 |        1 |     96% |        34 |
| **TOTAL**                        | **1920** |  **119** | **94%** |           |


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