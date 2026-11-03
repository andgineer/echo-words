# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/andgineer/echo-words/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                 |    Stmts |     Miss |   Cover |   Missing |
|------------------------------------- | -------: | -------: | ------: | --------: |
| src/echo\_words/\_\_about\_\_.py     |        2 |        0 |    100% |           |
| src/echo\_words/anki.py              |      694 |       39 |     94% |130, 146, 233, 240, 247, 250, 266, 410-412, 414, 487, 499, 532, 619, 644, 667, 745, 786, 937, 973-975, 1005, 1025, 1048, 1067, 1090, 1095, 1138, 1207, 1282-1283, 1290-1291, 1298-1299, 1317-1319 |
| src/echo\_words/api.py               |      370 |       21 |     94% |87, 132, 160, 170, 210, 426-428, 437-438, 463-464, 481-484, 558, 562-563, 581-582 |
| src/echo\_words/api\_backend.py      |       17 |        0 |    100% |           |
| src/echo\_words/audio.py             |      292 |       24 |     92% |93-95, 136, 140, 147-150, 160-161, 198-200, 221, 253-254, 456, 501-505, 511 |
| src/echo\_words/backend.py           |      309 |        4 |     99% |407, 573-576, 597 |
| src/echo\_words/broker.py            |       36 |        0 |    100% |           |
| src/echo\_words/card.py              |      272 |       16 |     94% |134-135, 192-193, 251-261, 266, 290, 295, 341, 353, 363, 483, 597 |
| src/echo\_words/config.py            |       52 |        0 |    100% |           |
| src/echo\_words/events.py            |       34 |        0 |    100% |           |
| src/echo\_words/history.py           |      117 |        0 |    100% |           |
| src/echo\_words/i18n.py              |       23 |        0 |    100% |           |
| src/echo\_words/language\_catalog.py |       22 |        0 |    100% |           |
| src/echo\_words/languages.py         |      270 |        2 |     99% |  107, 457 |
| src/echo\_words/lexicon.py           |       82 |        1 |     99% |       168 |
| src/echo\_words/llm\_backend.py      |       63 |        0 |    100% |           |
| src/echo\_words/logs.py              |       14 |        0 |    100% |           |
| src/echo\_words/main.py              |       44 |        0 |    100% |           |
| src/echo\_words/pipeline.py          |      895 |       37 |     96% |119, 129, 282, 434, 465, 557, 599, 616, 666, 846, 856-857, 914, 950-951, 1144, 1163, 1170-1171, 1214, 1274-1277, 1478, 1495, 1520, 1523, 1542, 1553, 1557, 1764, 1776, 1817-1820 |
| src/echo\_words/prompt.py            |      214 |        1 |     99% |       635 |
| src/echo\_words/sanitizer.py         |       89 |        0 |    100% |           |
| src/echo\_words/segments.py          |      108 |        6 |     94% |45, 77, 110, 114, 137, 209 |
| src/echo\_words/voices.py            |        9 |        0 |    100% |           |
| **TOTAL**                            | **4028** |  **151** | **96%** |           |


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