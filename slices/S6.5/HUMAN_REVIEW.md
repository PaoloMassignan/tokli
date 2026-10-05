# S6.5 — Human verification of the dashboard (Gate 2)

For the human, at the end of the slice. Answer each line with **ok**, or with what is wrong.

**Two passes:**
1. **The screenshots** produced by the agent: every page at 1280 px and 360 px, light and dark.
2. **The live dashboard with your own data.** Run `tokli serve` with your usual settings and
   open `http://127.0.0.1:8787/tokli/`.

## A. First impression (Overview, live, 10 seconds)

- [ ] Without reading any note, I can say how much Tokli saved in this range: tokens and money.
- [ ] I can tell whether the money figure is billed money or a value at API prices.
- [ ] Nothing on the first screen is decoration.
- [ ] Nothing looks generated: no gradients, glow, emoji, sparkles, oversized tiles or marketing
      words.
- [ ] I would not want to remove anything from the first screen.

## B. Each page

- [ ] **Overview.** The order of things matches their importance to me. The overhead chart says
      "target (not a limit)" and never "pass" or "fail".
- [ ] **Compressors:**
  - I see at a glance which compressors are on and what each saved;
  - the detailed figures are still reachable;
  - each compressor's kind is clear: lossless, selective or lossy.
- [ ] **Recent requests.** I can find a request and open its detail with the mouse and with the
      keyboard.
- [ ] **Settings:**
  - switching a compressor on or off is obvious;
  - the "Lossless only" shortcut is clear;
  - the explanations of the kinds read exactly as before;
  - a locked setting says why it is locked.

## C. Numbers and words

- [ ] Every number says how it was obtained: exact, calibrated or estimate. Money says
      "estimate" and shows a range.
- [ ] A missing value shows "—" with a reason I understand.
- [ ] The same thing has the same name everywhere.
- [ ] No sentence is longer or more technical than it needs to be.

## D. Small screen, dark mode, keyboard

- [ ] At phone width (360 px) nothing needs sideways scrolling of the page. Wide tables
      scroll inside their own box.
- [ ] Dark mode is readable, including charts and warnings.
- [ ] With the keyboard alone (Tab, Enter, Space) I can reach and use every control, and I can
      always see where the focus is.

## E. Nothing lost

- [ ] Everything I used before the review is still there, possibly in a new place. Note
      anything you miss.
- [ ] The dashboard still loads with the network cable unplugged (no external resources).

## Outcome

- Date:
- Result: accepted / changes requested
- Notes:
