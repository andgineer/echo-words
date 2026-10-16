# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/andgineer/echo-words/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                 |    Stmts |     Miss |   Cover |   Missing |
|------------------------------------- | -------: | -------: | ------: | --------: |
| src/echo\_words/\_\_about\_\_.py     |        1 |        0 |    100% |           |
| src/echo\_words/anki.py              |      694 |       39 |     94% |130, 146, 233, 240, 247, 250, 266, 410-412, 414, 487, 499, 532, 619, 644, 667, 745, 786, 937, 973-975, 1005, 1025, 1048, 1067, 1090, 1095, 1138, 1207, 1281-1282, 1289-1290, 1297-1298, 1316-1318 |
| src/echo\_words/api.py               |      368 |       21 |     94% |86, 131, 159, 169, 209, 423-425, 434-435, 460-461, 478-481, 555, 559-560, 578-579 |
| src/echo\_words/api\_backend.py      |       17 |        0 |    100% |           |
| src/echo\_words/audio.py             |      292 |       24 |     92% |95-97, 136, 140, 147-150, 160-161, 198-200, 221, 253-254, 456, 501-505, 511 |
| src/echo\_words/backend.py           |      309 |        4 |     99% |407, 573-576, 597 |
| src/echo\_words/broker.py            |       36 |        0 |    100% |           |
| src/echo\_words/card.py              |      269 |       17 |     94% |132-133, 190-191, 249-259, 264, 273, 278, 324, 330, 336, 346, 466, 581 |
| src/echo\_words/config.py            |       52 |        0 |    100% |           |
| src/echo\_words/events.py            |       34 |        0 |    100% |           |
| src/echo\_words/history.py           |      117 |        0 |    100% |           |
| src/echo\_words/i18n.py              |       23 |        0 |    100% |           |
| src/echo\_words/language\_catalog.py |       22 |        0 |    100% |           |
| src/echo\_words/languages.py         |      263 |        2 |     99% |  106, 456 |
| src/echo\_words/lexicon.py           |       82 |        1 |     99% |       169 |
| src/echo\_words/llm\_backend.py      |       63 |        0 |    100% |           |
| src/echo\_words/logs.py              |       14 |        0 |    100% |           |
| src/echo\_words/main.py              |       44 |        0 |    100% |           |
| src/echo\_words/pipeline.py          |      892 |       38 |     96% |119, 129, 276, 428, 459, 551, 593, 610, 660, 840, 850-851, 908, 944-945, 1137, 1155, 1162-1163, 1206, 1266-1269, 1470, 1487, 1512, 1515, 1534, 1545, 1549, 1647, 1756, 1768, 1809-1812 |
| src/echo\_words/prompt.py            |      214 |        1 |     99% |       631 |
| src/echo\_words/sanitizer.py         |       89 |        0 |    100% |           |
| src/echo\_words/segments.py          |      107 |        9 |     92% |44, 76, 106, 108, 112, 117, 135, 139, 207 |
| src/echo\_words/voices.py            |        9 |        0 |    100% |           |
| **TOTAL**                            | **4011** |  **156** | **96%** |           |


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