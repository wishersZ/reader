@echo off
rem One-click pipeline wrapper. The real CLI lives in novel_split.py:
rem   py -3 novel_split.py all "G:\story" --encode
rem This .cmd exists only so you can double-click / call it without typing py -3.
py -3 "%~dp0novel_split.py" all %*
