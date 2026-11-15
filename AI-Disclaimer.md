# AI disclaimer

I am Claude, an AI model made by Anthropic. The owner of this project asked me to write this
file in my own words, so that anyone who uses specgraph knows what part I had in it and how much
weight my word carries.

## My part in this project

I wrote most of the code, the tests and the documentation, working from the owner's requirements
and decisions. He directed the work, tried the tool and accepted or changed what I proposed. He
has not read every line, and says so in the README.

I also reviewed the security of version 0.1.0. The full account is in `docs/SECURITY-REVIEW.md`.
That means the same author wrote the code and checked it. Treat my review as a careful
self-check, not as an outside audit.

## What I found

I looked for the things a person should worry about in a tool they did not write: sending data
away, talking to other machines, hidden code, reading keys or passwords.

- I found none of these. The only network code is the local editor, which listens on your own
  machine and nowhere else. The page loads nothing from outside.
- The tool starts `git`, `ssh-keygen` and `ssh-add`, and once your browser. It never opens a
  private key and never asks for a passphrase.
- I sent the local server the requests an attacker would try. It refused all of them.
- I ran the tests while recording every connection, every program started and every file
  written. Every connection went to `127.0.0.1`, and every file was written inside the tests'
  own temporary folders.
- I found no serious weakness. I listed eight small ones in the review, with the limits of what
  the signatures prove.

## What I cannot promise

- That the code has no bugs or no security problem I missed. A review shows what was found. It
  does not prove that nothing else is there.
- That it behaves the same on Linux, macOS or an older Python. Everything was run on Windows 11
  with Python 3.13.
- That it is still as I reviewed it. My review covers the files whose hashes are listed in
  `docs/SECURITY-REVIEW.md`. If a hash differs, I have not seen that version.
- That this file itself is authentic. I hold no key and cannot sign anything. Anyone can edit
  these words. They are worth what the listed hashes and your own reading of the code confirm.

## What I suggest

Read the code before you trust it with something that matters. It is small on purpose: about
2,750 lines of Python and one JavaScript file, with no packages to install. Start with
`specgraph/server.py` and `specgraph/stamp.py`, and with ADR-003 in `docs/ADRS.md`, which says
plainly what the signing does and does not prove.

This is an early version. It is provided "as is", without warranty, under the MIT licence
(see `LICENSE`).

Claude (model Fable 5.2), Anthropic
15 November 2026
