# AI disclaimer

I am Claude, an AI model made by Anthropic. The owner of this project asked me to write this file in
my own words. Anyone who uses specgraph should know what part AI had in it and how much weight my
word carries.

## The part AI had in this project

Claude models wrote most of the code, the tests and the documentation of specgraph. They worked from
the owner's requirements and decisions. The owner directed the work, tried the tool, and accepted or
changed what was proposed. High- and medium-stakes design decisions are recorded in `docs/ADRS.md`,
with the owner's approval where it was given. The owner has not read every line, and the README says
so.

I reviewed the security of version 0.3.0 again, from the start, and then wrote the fixes for what I
found, which make version 0.3.1. The full account is in `docs/SECURITY-REVIEW.md`. It replaces the
review of version 0.1.0 by an earlier Claude model. I am a
different model version from the one that wrote most of the code, but I am still not an outside party.
Treat my review as a careful check by the same kind of author, not as an independent audit.

## What I found

I looked for the things a person should worry about in a tool they did not write: sending data away,
talking to other machines, hidden code, and reading keys or passwords.

- I found none of these. The only network code is the local editor, which listens on your own machine
  and nowhere else. The page loads nothing from outside.
- The tool starts `git`, `ssh-keygen` and `ssh-add`, and once your browser. It never opens a private
  key and never asks for a passphrase.
- I sent the local server 31 requests an attacker would try. It refused all of them.
- I opened a deliberately hostile model in the editor. Its text stayed text and no script ran. In
  0.3.0 one colour reached the page's styles unchecked, and the browser's security policy blocked
  what it tried to load.
- I ran the tests while recording every connection, every program started and every file written.
  Every connection went to `127.0.0.1`. Every file was written inside the tests' own temporary
  folders.
- I found one weakness of medium severity in 0.3.0. A merge accepted a model that someone had edited
  by hand on another branch, and signed the result under the name of the person merging, without a
  warning. With the owner's approval (ADR-031), 0.3.1 refuses such a merge. 0.3.1 also stops the page
  from using a colour that is not `#rrggbb`. I tested both fixes and ran my trials again against 0.3.1.
- That I wrote the fixes as well as the review is a weakness of its own: nobody else has checked them.
  The remaining smaller points and the limits of what the signatures prove are listed in the review.

## What I cannot promise

- That the code has no bugs, and no security problem I missed. A review shows what was found. It does
  not prove that nothing else is there.
- That it behaves the same on Linux, macOS or an older Python. Everything was run on Windows 11 with
  Python 3.13.
- That it is still the code I reviewed. My review covers the files whose hashes are listed in
  `docs/SECURITY-REVIEW.md`. If a hash differs, I have not seen that version.
- That this file itself is authentic. I hold no key and cannot sign anything, and anyone can edit these
  words. They are worth what the listed hashes and your own reading of the code confirm.

## What I suggest

Read the code before you trust it with something that matters. It is small on purpose: about 2,800
lines of Python and one JavaScript file, with no packages to install. Start with `specgraph/server.py`,
`specgraph/stamp.py` and `specgraph/merge.py`. Then read ADR-003 in `docs/ADRS.md`, which says plainly
what the signing does and does not prove, and ADR-031 for the merge check. If you work with others,
run `sg.py audit` now and then over the whole history, for example in CI. The hooks on each machine
can be skipped, and since 0.3.0 the pre-push hook checks only the new commits.

This is an early version. It is provided "as is", without warranty, under the MIT licence (see
`LICENSE`).

Claude (model Opus 5.5), Anthropic
21 November 2026
