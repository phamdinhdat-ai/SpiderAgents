# Spider appearance and Project → Chat fixes

## Using the theme

Open the gear icon in the header (**Appearance Settings**).

- **Spider-Verse**: red / blue.
- **Symbiote**: crimson / graphite; selecting it also enables dark mode.
- **Neon Web**: violet / cyan.
- **Spider Studio**: copper / sage.

Selecting an identity resets its color overrides while preserving radius/font
preferences. The primary, secondary, web-thread and background colors can then
be customized independently. The primary button text chooses a light or dark
foreground for contrast. Preferences persist in browser local storage, using
the existing appearance system; they do not require database migrations.

The Spider web background and project hero use original vector artwork: a
suspended spider, a polygonal web, traveling thread signals, and pulsing nodes.
The master Animations switch stops these effects; the operating system's
`prefers-reduced-motion` setting is also respected. The existing particle
background now respects the same switch and uses the secondary palette color.
Reset defaults returns to Spider-Verse, the web background, and system light/dark
appearance. Existing saved background and color preferences remain on upgrade.

## Navigation fixes

The old PageTransition cached React router children and ran a 150ms timer. A
parent rerender could cancel that timer after the path ref had advanced,
leaving the content in fade-out. Updates at the same URL could also retain old
route props. Regression tests reproduced both failures before the fix.

PageTransition now renders current children directly and applies a short,
cancelable incoming animation to the existing DOM wrapper. It never hides the
route or remounts a running chat just to animate it. Its full-height wrapper
also restores the chat layout, including the bottom composer.

Projects now hand the canonical backend ChatSpec to the session adapter before
navigating, both for new chats and existing conversation links. An older chat
list response cannot drop that explicit selection. Slow history responses no
longer overwrite the globals or selection callback of a more recently selected
chat. Project creation responses are also ignored for navigation if the user
has since switched project or agent; the conversation remains saved under its
original scope.

## Validation

- 12 targeted tests: route rerender races, project chat identity, stale list and
  history responses, palette persistence/reset/validation, and Projects UI.
- 30 regression tests: theme toggle, request handling, and agent store.
- TypeScript compilation and scoped lint are checked. Repository-wide lint has
  existing errors unrelated to these changes (see `logs/chat-theme-full-lint.log`).
- Chrome with the isolated preview API: repeated Project → Chat → Project,
  visible full-height composer, and the outgoing canonical project session ID.
  The reply endpoint was intercepted with synthetic SSE for this sender check;
  no LLM or infrastructure action was executed.
- Chrome also checks palette selection, three independent custom colors,
  persistence after reload, animation toggle, reduced motion and 390px mobile.
  Result: `logs/chat-theme-browser-result.json`; screenshots: `logs/spider-*.png`.

GitNexus upstream impact for the modified UI functions is LOW. The session
adapter helpers each have one direct caller and two total dependants in the
static graph, with no indexed execution processes; the outer adapter API is
invoked by the chat library. Application theme changes affect `App` through
ThemeProvider/AppInner. Aggregate change detection also includes the earlier
Projects implementation and must be read with that broader scope in mind.
