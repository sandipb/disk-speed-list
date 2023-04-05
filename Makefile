.PHONY: build check fmt sync

build: speed.html

check:
	mypy .

fmt:
	black *.py

speed.html: speed.markdown
	grip --export $<

sync: check
	rsync -a test_speed.py isengard:
