# Contributing

**English** · [Português](CONTRIBUTING.pt-BR.md)

This project wants first-time contributors. If you have never opened a pull
request, this is a good place for your first one — and this file assumes you
never have.

Nothing here is a stupid question. If something in this text confused you,
that is a bug in the text:
[open an issue](https://github.com/ONiceasNeto/babelt/issues/new/choose)
saying what was unclear.

> **Language.** You are welcome to write issues and pull requests in English,
> Portuguese or Spanish. babelt's own interface messages are in Portuguese
> today, and translating them is one of the open contributions listed below.

## Contents

- [The most useful contribution needs no code](#the-most-useful-contribution-needs-no-code)
- [Running the project on your machine](#running-the-project-on-your-machine)
- [Opening a pull request, step by step](#opening-a-pull-request-step-by-step)
- [What CI checks](#what-ci-checks)
- [Where to make changes, and what to read first](#where-to-make-changes-and-what-to-read-first)

---

## The most useful contribution needs no code

**Reporting a bad translation.** Really. babelt is measured by how much it
gets right on real text, and every example of odd output is quality data that
exists nowhere else. It is worth more than code.

How to do it:

1. Run `babelt <some command>` — for example `babelt tar`, `babelt find`.
2. Find a line that came out wrong, meaningless, or that should have been
   translated and was not.
3. Open the **Bad translation** issue and fill in the three fields it asks
   for: the command, the output you saw, and what is wrong with it.

You do not need to know *why* it is wrong. "This makes no sense" is a complete
report.

Other ways to help without writing Python:

- **Test on another distro.** The installer has been validated on Ubuntu
  24.04, Arch and Fedora 44 (Python 3.14) — the Fedora run used `--no-model`,
  so the model download is still unexercised there. openSUSE and Debian stable
  have not been tested at all. (Alpine cannot work yet: `ctranslate2`
  publishes no musl wheel.) Running `./install.sh` on one of them and
  reporting what happened is a whole contribution.
- **Improve the documentation.** Including this file.
- **Translate babelt's own messages.**

---

## Running the project on your machine

You need **Python 3.11 or newer** and Linux. To check your version:

```console
$ python3 --version
```

### 1. Get the code

```console
$ git clone https://github.com/ONiceasNeto/babelt
$ cd babelt
```

### 2. Create a virtual environment

A *virtual environment* (venv) is a folder where the project's libraries stay
isolated from the rest of your system. Without one, installing babelt's
dependencies could break another program of yours.

```console
$ python3 -m venv .venv
```

If it fails saying the `venv` module is missing, on Ubuntu/Debian/Mint install
it with `sudo apt install python3-venv`.

### 3. Install babelt in editable mode

```console
$ .venv/bin/pip install -e '.[dev]'
```

The `-e` means *editable*: Python uses the files in this folder directly, so
every change you make takes effect immediately, without reinstalling. The
`[dev]` brings the testing tools along.

> **Do not use `./install.sh` for development.** That script exists for people
> who only want to run the program: it copies the code into a separate venv,
> and your edits would have no effect.

### 4. Run the tests

```console
$ .venv/bin/pytest
```

They should all pass. If any fail **before** you change anything, that is
already an issue — please open one.

Tests that load the translation model (230 MB) are skipped automatically if
you do not have it. To run only what does not need it:

```console
$ .venv/bin/pytest -m 'not model'
```

### 5. (Optional) Download the model

Only needed if you want to actually **run** babelt, not to work on most of the
code:

```console
$ .venv/bin/babelt ls
```

It asks before downloading.

---

## Opening a pull request, step by step

A *pull request* (PR) is the request "please take my change". There are six
steps and none of them is irreversible.

### 1. Fork the repository

On the [project's GitHub page](https://github.com/ONiceasNeto/babelt), click
**Fork**, top right. That creates a copy of the repository under your account,
which is yours to break freely.

### 2. Clone *your* fork

Replace `YOUR-USERNAME` with your GitHub username:

```console
$ git clone https://github.com/YOUR-USERNAME/babelt
$ cd babelt
```

### 3. Create a branch

A *branch* is a parallel line of work. Working on a branch rather than
directly on `main` lets you touch several things without mixing them together.

```console
$ git checkout -b fix-tar-translation
```

The name is up to you; use something that describes the change.

### 4. Make the change and commit it

```console
$ git add .
$ git commit -m "fix translation of --wildcards in tar"
```

`git add .` stages everything you changed. `git commit` records a point in
history, with a message explaining what. A good message says **what changes
and why**, not "tweaks".

### 5. Push and open the PR

```console
$ git push origin fix-tar-translation
```

GitHub prints a link in your terminal. Open it, click **Create pull request**,
write what you changed and why, and submit.

### 6. Wait for review

CI runs on its own and tells you if something broke. If it does, that is not a
problem: it is the system doing its job. Make more commits on the same branch
and push again — the PR updates itself.

Bad-tempered review is not accepted here. If a review comment reads as rude,
tell me.

### If something goes wrong

- **I committed on the wrong branch.** Not committed yet? `git checkout -b
  right-name` carries the changes over.
- **I want to undo the last commit but keep what I wrote.**
  `git reset --soft HEAD~1`.
- **I am lost.** Delete the folder, clone your fork again, and start over.
  Nothing is lost in the original repository.

---

## What CI checks

Every time you push, GitHub runs three commands. These exactly, and you can
run all three on your own machine before submitting:

```console
$ .venv/bin/pytest -m 'not model'                 # tests, without the 230 MB model
$ .venv/bin/mypy                                  # type checking, strict mode
$ .venv/bin/mypy --python-version 3.11 babelt     # type checking on the oldest supported Python
```

If those three pass locally, CI passes.

The third exists because the project supports Python 3.11 onwards, and it is
easy to accidentally write something that only works on 3.12. It checks that
without you having to install 3.11.

Additionally, if you touch `install.sh`, run `shellcheck`. It does not come
with `[dev]` or with the system; install it one of these ways:

```console
$ .venv/bin/pip install shellcheck-py       # works on any distro
$ sudo apt install shellcheck               # Debian/Ubuntu/Mint
$ sudo pacman -S shellcheck                 # Arch
```

And then:

```console
$ .venv/bin/shellcheck install.sh           # if installed via pip
$ shellcheck install.sh                     # if installed from the distro
```

### About writing tests

Every behaviour change needs a test. The project's rule is: **the test fails
before the fix and passes after it.** Write it first, watch it fail, and only
then fix the code — if it passes before the fix, it is not testing what you
think it is.

Tests live in `tests/`, one file per module. Comments explaining *why* a test
exists are welcome: almost every test there answers a real defect, and knowing
which one helps whoever comes next. Existing comments are in Portuguese;
English is fine for new ones.

---

## Where to make changes, and what to read first

| If you want to... | Change | Read first |
| --- | --- | --- |
| Fix a word translated wrongly | `babelt/glossary.txt` | — |
| Stop a term from being translated | `babelt/literals.txt` | — |
| Translate a new section header | `babelt/headers.txt` | — |
| Protect syntax that is being translated | `babelt/mask.py` | [phases 1 to 1.2](docs/development/) |
| Change how text is split | `babelt/segment.py` | [phases 2 and 5](docs/development/) |
| Change when a translation is rejected | `babelt/validate.py` | [phase 3.1](docs/development/) |

The first three are plain text files, one entry per line. They are the best
place for a first code contribution.

**The rules in `mask.py`, `segment.py` and `validate.py` are not arbitrary.**
Each one answers a false positive or false negative measured on a real corpus,
and several obvious hypotheses have already been tested and rejected. The
history is in [`docs/development/`](docs/development/), with the numbers.
Reading the relevant phase before changing a regex saves you from walking a
path that has already been walked.

Those documents are in Portuguese. If that is a barrier for the change you
want to make, say so in the issue — it is worth translating the parts that
matter, and that is itself a welcome contribution.

---

## Code of conduct

Treat people well. Beginners get priority on everyone's patience. Behaviour
that makes someone give up on contributing is not tolerated, however
technically correct it may be.
