[![Build Status](https://github.com/andgineer/echo-words/workflows/CI/badge.svg)](https://github.com/andgineer/echo-words/actions)
[![Coverage](https://raw.githubusercontent.com/andgineer/echo-words/python-coverage-comment-action-data/badge.svg)](https://htmlpreview.github.io/?https://github.com/andgineer/echo-words/blob/python-coverage-comment-action-data/htmlcov/index.html)
# echo-words

Turns words into rich linguistic insights and automatically adds them to your spaced repetition system. 

# Documentation

[Echo Words](https://andgineer.github.io/echo-words/)



# Developers

Do not forget to run `. ./activate.sh`.

For work it need [uv](https://github.com/astral-sh/uv) installed.

Use [pre-commit](https://pre-commit.com/#install) hooks for code quality:

    pre-commit install

## Allure test report

* [Allure report](https://andgineer.github.io/echo-words/builds/tests/)

# Scripts
Install [invoke](https://docs.pyinvoke.org/en/stable/) preferably with [uv tool](https://docs.astral.sh/uv/):

    uv tool install invoke

For a list of available scripts run:

    invoke --list

For more information about a script run:

    invoke <script> --help

## Coverage report
* [Codecov](https://app.codecov.io/gh/andgineer/echo-words/tree/main/src%2Fecho_words)
* [Coveralls](https://coveralls.io/github/andgineer/echo-words)

> Created with cookiecutter using [template](https://github.com/andgineer/cookiecutter-python-package)
