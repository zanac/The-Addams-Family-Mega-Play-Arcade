# The Addams Family ARCADE — Mega Play conversion (`mp_addams`)

Technical notes for the Sega Mega Play version of the v77.0 arcade build.
Everything below was measured in mame2003-plus (libretro) with a headless
frontend, using `mp_sor2` (Streets of Rage II) as the reference game.

## 1. What a Mega Play set is

| File | Size | Role |
|---|---|---|
| `epr-26013.ic1` | 2 MB | 68000 game ROM, **word-swapped** like Sega's dumps (`ROM_LOAD16_WORD_SWAP`) |
| `epr-15175-20.ic2` | 32 KB | Game instruction ROM: title, instruction screen, GAME SETTING page and the game-specific Z80 code the BIOS runs |
| `megaplay.zip` | — | Shared BIOS (`ep15294.ic2`), unchanged |

File names follow Sega's scheme: `epr-` (EPROM) + part number, `.icN` = board
position. `15175` is the part number Sega gave to every Mega Play instruction
ROM (`-01` Sonic … `-09` Shinobi III); `-20` stays clear of the real ones.
`26013` is an invented part number for the homebrew game EPROM. The set
itself is still `mp_addams.zip`.

The instruction ROM is visible to the 68000 at `0x300000-0x30FFFF` (each byte
doubled) and to the BIOS Z80 through its bank window.

## 2. Build

> End users: see `README.md` (original ROM + IPS + `make_mp_addams.py`).
> This section describes the developer build from the v77.0 ROM and the
> assembler source, shipped in the full development package.

```
./build_mp.sh Addams_Family_ARCADE_v77.0.bin mp_sor2.zip [out]
```

* Input 1: the v77.0 ROM (MD5 `A81B33DB12EFCD3FFBBDFF96BE81FBBA`).
* Input 2: the user's `mp_sor2.zip`. Two things are taken from it, so no Sega
  code is shipped with this package:
  * the BIOS protocol routines (SOR2 `0x3AB28-0x3B0C0`), relocated to `0x110000`;
  * the instruction ROM `epr-15175-05.ic2`, used as a template.
* Output: `mp_addams.zip` and the plain big-endian `Addams_Family_ARCADE_MP.bin`.
* `--debug` builds a ROM that writes every BIOS↔game command to `$B00000/$B00002`,
  where MAME's unmapped-write log shows it.

Needs `python3` and the m68k GNU binutils (`binutils-m68k-linux-gnu`).

## 3. Emulator side (mame2003-plus)

Target: **github.com/zanac/mame2003-plus-libretro**, on top of `eb611be`
("Backport for mp_gslam and mp_mazin on mega play"). Apply either file:

```
git am core/0001-Add-mp_addams.patch
#   or
git apply mame2003-plus_mp_addams.diff
make
```

The patch adds to `src/drivers/segac2.c` and `src/driver.c`:

* `INPUT_PORTS mp_addams` with the game's DSW C;
* machine `megaplay_nvram` = `megaplay` + an NVRAM handler that saves the BIOS
  battery RAM (Z80 `0x6800-0x77FF`): credits, bookkeeping and the per-slot
  256-byte game areas (our high scores). Without it nothing survives a restart;
* `ROM_START mp_addams` (`epr-26013.ic1`, `epr-15175-20.ic2`, shared BIOS),
  `GAMEB` and `DRIVER` entries.

The fork's `megaplay` machine already has `MDRV_VIDEO_EOF(segac2)`. Stock
upstream mame2003-plus does not: there the VDP VBLANK status bit stays at 1 and
the boot screen's frame waits all run into their time-out (~50 s instead of 8),
so on stock upstream add it to `megaplay_nvram` as well.

The fork also models the BIOS-driven Start line of the real board (§4.5); the
ROM works with both behaviours.

## 4. The BIOS ↔ game link

### 4.1 Wire protocol
16-bit words over joypad port C (`$A10007`), three bits each way; control
register `$A1000D = $47`. The routines are SOR2's, relocated:

| New | SOR2 | Function |
|---|---|---|
| `0x110000` | `0x3AB28` | handshake: finds the slot, stores `$A02000 + n*$800` in `$FFF2E4` |
| `0x11006A` | `0x3AB92` | receive a word (non-blocking) |
| `0x110152` | `0x3AC7A` | send a word |
| `0x1102EE` | `0x3AE16` | per-frame heartbeat |
| `0x11049E` | `0x3AFC6` | poll and dispatch one BIOS command |

**Pitfall:** the game's pad initialisation writes `$40` to `$A1000D`, which turns
the port-C output bits into inputs and kills the link (the first send then
loops for ever). `MPFRAME` writes `$47` back every frame.

**Pitfall:** the BIOS resets the 68000 if the game stops answering. The boot
screen runs with interrupts off, so its per-frame wait (`0x1018DA` → `0x106F00`)
now also calls `MPPOLL` (heartbeat and dispatch).

### 4.2 Shared slot area (`$A02000 + n*$800`, Z80 bus requested)

| Offset | Meaning |
|---|---|
| `+0` | DSW C, inverted, low nibble only (`~DSWC & $0F`) |
| `+1` | BIOS credit count, **capped at 9**; `$FF` = free play |
| `+$700..$7FF` | game area; the BIOS copies it to battery RAM at the end of a game (state 4 exit, after `$FF04`) and restores it at power-on |

### 4.3 Commands, BIOS → game (dispatcher table, SOR2 order)

| Code | Meaning / our handler |
|---|---|
| `FFF8` / `FFF9` | hold until `FFF9` / release (SOR2 code) |
| `FF80 FF88 FF8D FF90` | test-mode helpers (SOR2 code, unchanged) |
| `FF85` | BIOS RAM test, then wait for the BIOS reset |
| `FF02` | credits present → we answer `FF1D` |
| `FF1B` | → we answer `FF1C` |
| `FF01 FF03 FF0A FF8E` | ignored |

### 4.4 Commands, game → BIOS (measured)

| Code | Effect |
|---|---|
| `FF0A` | 1P start: takes one credit and switches the BIOS to "in game" (its INSERT COIN / CREDIT overlay disappears). Ignored when already in game |
| `FF09` | 2P start: takes two credits |
| `FF1A` | sent by SOR2 after `FF0A`; no credit effect |
| `FF04` | game over: back to attract (overlay returns, game area backed up) |
| `FF14` | **in our instruction ROM**: take one credit now (continue) |
| `FF15` | **in our instruction ROM**: give one credit back (refused password) |

`FF14` was SOR2's "player 1 back in" handler inside the instruction ROM
(`0x41AB`, Z80 code run by the BIOS). It is rewritten to
`call 0x0134` (BIOS vector → `0x1546`, which decrements the credit count, skips
free play and updates the battery copy). A continue cannot use `FF0A`: the
BIOS only honours it from attract.

`FF15` (SOR2: player 2 joins, `0x41C0`) is redirected to new code at `0x41B6`,
the inverse of `0x1546`: skipped in free play, capped at 9, then credits,
display copy and battery copy written and the battery checksum updated
(`call 0x151B`).

### 4.5 The Start button during a game
On the real board the pad's Start line reaches the game through the BIOS
(`$6203` bit 4 = P1, bit 5 = P2, active low): the BIOS reads the button on its
own port and, during a game, keeps the line released, passing a press on only
for its own continue/join logic (SOR2's `FF20`/`FF11` path). The zanac fork
emulates this, stock mame2003-plus wires the button straight to the pad.

Our continue, password and initials screens read Start directly, so on the
fork the continue START was ignored. The instruction ROM's in-game loop
(`0x40AB`, which called `0x4149`) now calls `0x43B0` first: it copies the P1
Start button (`$6914` bit 6, set by the BIOS input scan) to `$690A`/`$6203`
bit 4, then jumps to `0x4149`. Outside a game the BIOS handles the line as usual
(it passes Start on the title only when there is a credit).

## 5. Changes to the v77 code

| Address | Was | Now |
|---|---|---|
| `0x000300` | `jmp $104000` | `jmp MPBOOT` (handshake first) |
| `0x104986` | `jmp $101B00` (boot screen) | `jmp MPBOOTSCR` (cold/warm start) |
| `0x101506` | `jsr $101300` (MODE reader, VBlank) | `jsr MPFRAME` |
| `0x074832`, `0x10068A`, `0x104940` | `subq.w #1,CREDITS` | `jsr MPCONS` |
| `0x10090C` | `addq.w #1,CREDITS` (password refund) | `jsr MPREFUND` |
| `0x106E00` | DIPENTRY (settings load + service menu) | `jsr MPDIPS` + `jmp GAME_INIT` |
| `0x106F00` | WAITLATCH (MODE+DOWN latch) | `jsr BOOT_WAIT` + `jsr MPPOLL` |
| `0x107700` | CREDHUD | `jsr MPTITLE`, free-play fix-up, no digits |
| `0x0750B2` | `jsr DRAW_FRAME_PLANE` (title box) | removed |
| `0x104004…0x1053B0` | 9 SRAM accesses + 4 exits | slot-area helpers (§5.3) |
| `0x1B0` | `RA` SRAM declaration | blank |

New RAM (above the soft clear at `$FFEA5A`, unreferenced in v77):
`$FFF2E4` slot base (.l), `$FFF2E8` raw BIOS credits, `$FFF2EA` last BIOS count,
`$FFF2EC` credits spent and not yet reported, `$FFF2EE` Z80-bus nesting,
`$FFF2FA` saved SR, `$FFF2FC` flags, `$FFF2FE` reconcile hold-off.

### 5.0 The BIOS resets the cartridge
Besides the watchdog, the BIOS resets the 68000 on its own as part of normal
operation: twice during its power-on sequence, on the first coin while it is
in attract, and when a game ends (`FF04`). Each reset re-runs our boot code.
Without care this showed the boot screen (fake RAM/ROM test) for a moment
— the "garbled frames" seen on the return to the title. The same transitions
on the cartridge build (v77 in Genesis Plus GX) are clean.

`MPBOOTSCR` (on the boot chain at `0x104986`) keeps a marker `ADMS` at
`slot+$6F0`. The BIOS clears `slot+$000..$6FF` only at its own power-on, so:
marker absent = cold start (boot screen, then marker written); marker present
= reset by the BIOS (straight to settings and the game). The high-score area
`slot+$700` is not touched.

### 5.1 Credits
The arcade code is unchanged; only the source of the coin moved.

* Each frame `MPFRAME` reads the BIOS count. A rise of *n* adds *n* to
  `CREDITS` (cap 9) and plays coin sound `$42`, exactly what the MODE reader
  did. Every screen that already reacted to `CREDITS` keeps working.
* `MPCONS` (the three spending points) decrements `CREDITS` and queues a
  report. The next VBlank sends `FF0A`+`FF1A` for a new game, or `FF14` for a
  continue.
* A refused password refunds the credit (`0x100900`, v77 behaviour). The
  credit was already taken by the BIOS when PASSWORD was chosen, so the
  refund point (`0x10090C`) now calls `MPREFUND`, which also queues `FF15`.
  Without it the reconcile step put the counter back to the BIOS value and
  the refund was lost.
* When nothing is in flight for 2-3 s, `CREDITS` is aligned to the BIOS count,
  so the two can never drift for long.
* `$FF` from the BIOS sets `SET_FREE` (free play is now the coinage DIP).

Not reporting decrements does **not** work: the BIOS count stops at 9, refuses
further coins, and the game would never see another one.

### 5.2 Settings
The service menu is gone; `MPDIPS` reads DSW C at boot.

| DSW C bits (inverted) | 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| 0-1: pickups per 1UP | 3 | 2 | 1 | 3 |
| 2-3: lives per credit | 3 | 5 | 7 | 99 |

Coinage and free play are the BIOS DSW A/B.

### 5.3 High scores
The cartridge has no SRAM on Mega Play (`0x200000` is ROM space; writes are
lost). The table keeps its odd-byte layout and moves from `$2000xx` to
`slot+$7xx` (`$200011` → `slot+$711`; 96 bytes used of 256). Each access
helper requests the Z80 bus with interrupts off; the routine's exit releases it
(the row printer releases it before printing).

`FF04` is sent from the title loop once a game is over **and** the initials
have been entered (`$FFF34E != 1`); sending it earlier put the BIOS overlay on
top of the initials screen.

### 5.4 Instruction ROM
From SOR2's: title `THE ADDAMS / FAMILY`, new instruction text at `0x2000`
(`FE` new line, `FC n c` = *n* times character *c*, `FF` end), GAME SETTING
labels and value tables at `0x35D/0x37C/0x39C`, the `FF14`/`FF15` handlers,
the Start pass-through at `0x43B0` (§4.5) and the overlay positions (§5.5).

### 5.5 Where the BIOS writes on our title
Outside a game the BIOS draws two lines with its own video chip, on top of
the game. Their positions are **per game**, in the instruction ROM header:
two tables of eight SMS name-table addresses (`$7800 + row*64 + col*2`) read
by the BIOS at `0x0E93` (offset `$38`: CREDIT / FREE PLAY line) and `0x0EA3`
(offset `$48`: INSERT COIN(S) / PUSH START line). SOR2 puts them on rows 21-23
and 17, right across our menu and high-score table; ours are on row 0 col 2
and row 1 col 1. Column 0 is outside the picture (it cut the F of FREE PLAY).

The message line cannot go fully left: the BIOS strings carry their own
centring blanks (`FC 05 1F PUSH 1P START BUTTON`, `1F 1F PUSH 1P or 2P …`,
`FC 07 1F INSERT COIN(S)`), so the line always ends near the right edge.
That is where our title credit box was, so on Mega Play the title no longer
draws it: CREDHUD (`0x107700`) skips the digits and the frame call at
`0x0750B2` is removed. The box is still drawn in game, on the continue screen
and on the initials/password screen, where the BIOS shows nothing.

## 6. Known differences from the cartridge version

* **The BIOS overlay.** Outside a game the BIOS writes CREDIT and INSERT
  COIN(S) / PUSH START on the top two rows (§5.5) and, periodically, shows its
  logo and instruction screen full-screen, as on every Mega Play title. It
  cannot be switched off without losing the end-of-game battery backup (§4.2).
* Six-button features are gone (3-button pads): no MODE coin, no service menu.

## 7. Test log

Headless libretro frontend, zanac fork `eb611be` + this patch (release
core), and stock upstream `74a1af5` + the same driver additions.

### Results

| Test | Result |
|---|---|
| boot, handshake, boot screen at normal speed | OK |
| coin → credit counter; coin during play | OK |
| START → BIOS count −1, overlay off | OK |
| death by timer ×3 → continue screen | OK |
| coin + START on continue → BIOS count −1, play resumes | OK |
| game over → initials → table written to slot area | OK |
| restart emulator → record still in the table | OK (with the NVRAM patch) |
| DSW C lives = 5 | OK |
| free play (DSW A = 00) | OK, counters hidden, demo runs |
| title: BIOS lines on rows 0-1, menu and table clear | OK |
| continue screen / in game: our credit box still drawn | OK |
| coin during attract demo → title, no boot-screen flash | OK |
| game over → BIOS reset → title, no boot-screen flash | OK |
| coin → PASSWORD → wrong code → credit back on the BIOS too; it starts a game | OK |
| continue START on the fork's BIOS-driven Start line | OK |
| same full sequence on stock upstream core | OK |
