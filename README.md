# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/andgineer/echo-words/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                             |    Stmts |     Miss |   Cover |   Missing |
|--------------------------------- | -------: | -------: | ------: | --------: |
| src/echo\_words/\_\_about\_\_.py |        1 |        0 |    100% |           |
| src/echo\_words/anki.py          |      465 |       27 |     94% |128, 132, 210, 217, 224, 275, 426, 462-464, 494, 514, 550, 586, 605, 628, 633, 638, 682, 851-852, 858-859, 863-866 |
| src/echo\_words/api.py           |      270 |       22 |     92% |72, 117, 134, 144, 184, 273-275, 284-286, 295-296, 302-305, 360, 364-365, 383-384 |
| src/echo\_words/api\_backend.py  |       17 |        0 |    100% |           |
| src/echo\_words/audio.py         |      201 |       26 |     87% |101, 103-105, 144, 148, 152-153, 164-167, 194-195, 220, 226, 241, 245-246, 307, 352-356, 362 |
| src/echo\_words/backend.py       |      167 |        3 |     98% |247-250, 271 |
| src/echo\_words/broker.py        |       28 |        0 |    100% |           |
| src/echo\_words/card.py          |      116 |        2 |     98% |  128, 213 |
| src/echo\_words/config.py        |       41 |        0 |    100% |           |
| src/echo\_words/events.py        |       34 |        0 |    100% |           |
| src/echo\_words/history.py       |       98 |        1 |     99% |       108 |
| src/echo\_words/i18n.py          |       23 |        0 |    100% |           |
| src/echo\_words/languages.py     |      112 |        1 |     99% |        72 |
| src/echo\_words/llm\_backend.py  |       38 |        0 |    100% |           |
| src/echo\_words/main.py          |       22 |        0 |    100% |           |
| src/echo\_words/pipeline.py      |      505 |       35 |     93% |175, 294, 324, 345, 366, 398, 407-408, 443, 494-495, 518-519, 545, 567-574, 728, 735, 744, 769, 772, 790-793, 797, 801, 848, 939 |
| src/echo\_words/prompt.py        |       46 |        0 |    100% |           |
| src/echo\_words/sanitizer.py     |       25 |        1 |     96% |        37 |
| src/echo\_words/segments.py      |       44 |        0 |    100% |           |
| src/echo\_words/shape.py         |       20 |        0 |    100% |           |
| **TOTAL**                        | **2273** |  **118** | **95%** |           |


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