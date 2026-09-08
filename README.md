# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/andgineer/echo-words/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                 |    Stmts |     Miss |   Cover |   Missing |
|------------------------------------- | -------: | -------: | ------: | --------: |
| src/echo\_words/\_\_about\_\_.py     |        1 |        0 |    100% |           |
| src/echo\_words/anki.py              |      573 |       35 |     94% |128, 144, 229, 236, 243, 259, 405, 430, 453, 531, 572, 723, 759-761, 791, 811, 834, 853, 876, 881, 924, 993, 1067-1068, 1075-1076, 1080-1084, 1102-1104 |
| src/echo\_words/api.py               |      344 |       22 |     94% |84, 129, 157, 167, 205, 384-386, 395-397, 406-407, 424-427, 493, 497-498, 516-517 |
| src/echo\_words/api\_backend.py      |       17 |        0 |    100% |           |
| src/echo\_words/audio.py             |      231 |       23 |     90% |69, 71-73, 112, 116, 123-126, 136-137, 184-185, 210, 216, 336, 381-385, 391 |
| src/echo\_words/backend.py           |      239 |        4 |     98% |264, 393-396, 417 |
| src/echo\_words/broker.py            |       28 |        0 |    100% |           |
| src/echo\_words/card.py              |      264 |       18 |     93% |133-134, 181-182, 240-250, 255, 264, 269, 315, 321, 327, 338, 402, 493, 517 |
| src/echo\_words/config.py            |       42 |        0 |    100% |           |
| src/echo\_words/events.py            |       34 |        0 |    100% |           |
| src/echo\_words/history.py           |      106 |        0 |    100% |           |
| src/echo\_words/i18n.py              |       23 |        0 |    100% |           |
| src/echo\_words/language\_catalog.py |       22 |        0 |    100% |           |
| src/echo\_words/languages.py         |      238 |        2 |     99% |  104, 434 |
| src/echo\_words/lexicon.py           |       82 |        1 |     99% |       169 |
| src/echo\_words/llm\_backend.py      |       53 |        0 |    100% |           |
| src/echo\_words/main.py              |       34 |        0 |    100% |           |
| src/echo\_words/pipeline.py          |      690 |       37 |     95% |109, 214, 350, 379, 438, 490, 500-501, 557, 748, 766, 773-774, 810, 853, 868-871, 1066, 1074, 1083, 1108, 1111, 1129-1132, 1136, 1140, 1222, 1313, 1325, 1366-1369 |
| src/echo\_words/prompt.py            |       72 |        2 |     97% |   307-308 |
| src/echo\_words/sanitizer.py         |       25 |        1 |     96% |        37 |
| src/echo\_words/segments.py          |      103 |        9 |     91% |40, 52, 74, 76, 80, 83, 101, 105, 173 |
| src/echo\_words/voices.py            |        9 |        0 |    100% |           |
| **TOTAL**                            | **3230** |  **154** | **95%** |           |


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