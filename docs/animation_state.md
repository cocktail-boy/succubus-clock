# Animation State Transitions

Reference for the video state machine in `index.html`. Read this before
changing interaction behavior or adding another variation set.

## Event Families

There are three kinds of full event playback and one inline branch:

1. Ambient variations
   - Source: `successfulVariations`
   - Videos: legacy `img_0001` through `img_0018`
   - Trigger: automatic after the anchor has completed an idle cycle
   - User interaction does not directly request these anymore

2. Close-up events
   - Source: `closeupVariationVideos`
   - Videos: `succubus_closeup_v01` through `succubus_closeup_v10`
   - Trigger: generic stage click, touch, or key press **while in anchor idle**
   - One pending close-up slot only

3. DWZ events
   - Source: `dwzVariationVideos`
   - Videos: `succubus_dwz_v01` through `succubus_dwz_v06`
   - Trigger: age estimator and bucket-list interactions
   - One pending DWZ slot only

4. Cute branch (inline detour, not a full event)
   - Source: `cuteBranchVideos`, indexed by ambient variation `id`
   - Videos: 18 forward (`regular_to_cute_concept_4s`) and 18 reverse
     (`cute_concept_to_regular_4s`), one pair per ambient variation
   - Trigger: generic stage click, touch, or key press **while in ambient
     variation idle**
   - One pending cute slot only; never reaches anchor; resumes the same ambient
     variation's idle on return

The first three families share the standard clip shape:

```text
anchor idle(s)
  -> anchor_to_variation_8s
  -> variation idle clips
  -> variation_to_anchor_4s
  -> anchor idle(s)
```

The cute branch is shorter and lives inside an ambient idle phase:

```text
ambient idle clip
  -> regular_to_cute_concept_4s   (specific to current ambient variation id)
  -> cute_concept_to_regular_4s   (specific to current ambient variation id)
  -> ambient idle clip (same variation, 4-idle counter continues)
```

## Core State

`nextVariationIndex`
: Index for the next automatic ambient variation.

`nextCloseupVariationIndex`
: Index for the next close-up event. Advances only when a new close-up is
reserved.

`nextDwzVariationIndex`
: Index for the next DWZ event. Advances only when a new DWZ event is
reserved.

`requestedCloseupVariation`
: Single pending close-up event slot. `null` means no close-up is reserved.

`requestedDwzVariation`
: Single pending DWZ event slot. `null` means no DWZ event is reserved.

`requestedCuteBranch`
: Single pending cute-branch slot, `{ id, forward, reverse }` matching the
ambient variation that was on screen when the stage was tapped. `null` means
no cute branch is reserved. Only consumed inside the ambient idle loop.

`currentAmbientVariation`
: The ambient variation video whose idle phase is currently playing, or
`null`. Set on entry to the ambient idle loop and cleared before the
variation-to-anchor reverse transition. Distinguishes anchor idle (null) from
ambient variation idle (non-null) for the stage-tap router.

`activeVariationEventType`
: Empty string for ambient events, for the cute branch, and during all
transition clips. Set to `closeup` or `dwz` only while that event is in its
variation-idle phase. This lets repeated interactions exit the current event
instead of queueing the next one.

`transitionRequested`
: Asks the current idle loop to end and move to the next transition.

`isTransitioning`
: True while a forward or reverse transition clip is playing. Interaction
requests are ignored during this period.

`idleClipQueues` and `idleClipPlayCounts`
: Shuffle and count idle clips per queue key. The anchor uses the literal key
`'anchor'`; each variation uses its `id`. Each key plays a four-idle cycle
before automatically returning.

## Phase Table

`isTransitioning` and `activeVariationEventType` together describe which phase
the state machine is in. Request handlers branch on this pair.

| Phase                          | `isTransitioning` | `activeVariationEventType` | `currentAmbientVariation` | Stage-tap behavior                                  |
| ------------------------------ | ----------------- | -------------------------- | ------------------------- | --------------------------------------------------- |
| Anchor idle                    | false             | `''`                       | null                      | Reserves a closeup event and ends current idle      |
| Forward transition (any event) | true              | `''`                       | null                      | Ignored                                             |
| Ambient variation idle         | false             | `''`                       | non-null                  | Reserves a cute branch for the current variation id |
| Cute branch (forward & reverse)| true              | `''`                       | non-null                  | Ignored                                             |
| Closeup variation idle         | false             | `closeup`                  | null                      | Requests return to anchor (no new reservation)      |
| DWZ variation idle             | false             | `dwz`                      | null                      | Ignored (stage tap does not interrupt DWZ idle)     |
| Reverse transition (any event) | true              | `''`                       | null                      | Ignored                                             |

## Request Rules

When a request "ends the current idle" or "requests return to anchor", it
sets `transitionRequested = true` and calls `skipActiveClip()`, which fast-
forwards the currently playing idle clip to its trim point so the next
transition begins within a frame instead of waiting for the idle to end
naturally.

### Stage-tap request (close-up or cute branch)

`requestCloseupVariation()` is the single entry point for stage click, touch,
and generic key press. It routes to either a close-up event or a cute branch
based on the current phase.

```text
if transition clip is active:
  ignore
else if current event type is closeup:
  request return to anchor (skipActiveClip)
else if currentAmbientVariation is non-null:
  delegate to requestCuteBranch
else if any event is active or pending (closeup, dwz, or cute):
  ignore
else (anchor idle):
  reserve next close-up
  prefetch it
  request current idle to end (skipActiveClip)
```

### Cute branch request

`requestCuteBranch()` is only called by the stage-tap router when
`currentAmbientVariation` is non-null. It reserves a cute branch keyed to that
variation's `id`. Unlike close-up and DWZ, it does **not** set
`transitionRequested`; the ambient idle loop handles the reservation inline.

```text
if transition clip is active:
  ignore
else if requestedCuteBranch is non-null:
  ignore
else if any full event is pending (closeup or dwz):
  ignore
else:
  look up cute pair by currentAmbientVariation.id
  reserve it as requestedCuteBranch
  prefetch it
  skipActiveClip   (only; do not set transitionRequested)
```

### DWZ request

`requestDwzVariation()` is called by age and bucket-list UI actions.

```text
if transition clip is active:
  ignore
else if current event type is dwz:
  request return to anchor (skipActiveClip)
else if any event is active or pending (closeup, dwz, or cute):
  ignore
else:
  reserve next DWZ event
  prefetch it
  request current idle to end (skipActiveClip)
```

Close-up, DWZ, and cute-branch requests intentionally do not stack. At most
one full event and one cute branch can be pending, and the cute-branch check
in the DWZ rule prevents a fast deck-tap from stranding a just-reserved cute
branch.

## Main Loop

`runVideoSequence()` is the only owner of playback order.

```text
forever:
  if a requested event exists:
    consume it
    playVariationEvent(event, eventType)
    continue

  play one anchor idle

  if no transition requested and anchor idle cycle is not complete:
    continue

  if a requested event exists:
    consume it
    playVariationEvent(event, eventType)
  else:
    play next ambient variation
```

`takePendingVariationEvent()` gives close-up priority over DWZ if both were
somehow set. In normal interaction flow this should not happen because request
functions refuse to reserve an event while another event is active or pending.

## Variation Event Loop

`playVariationEvent(variationVideo, anchorIdleClips, eventType)` handles all
three full event families. The cute-branch detour is handled inline when
`eventType === ''`.

```text
prefetch current variation and next ambient transition
play anchor -> variation transition
set activeVariationEventType to eventType
if eventType is '':
  set currentAmbientVariation to variationVideo
  prefetch the cute pair for variationVideo.id   (warm before first tap)

while no return requested and no pending full event:
  if eventType is '' and requestedCuteBranch is set:
    consume requestedCuteBranch
    isTransitioning = true
    play regular_to_cute_concept (preload cute_concept_to_regular as next source)
    play cute_concept_to_regular (preload next ambient idle clip as next source)
    isTransitioning = false
    continue   (do not advance the variation idle counter)

  play next shuffled idle clip for this variation
  advance idle counter
  if counter completed a four-clip cycle AND requestedCuteBranch is not set:
    request return to anchor

clear currentAmbientVariation (if it was set)
clear activeVariationEventType
play variation -> anchor transition
```

Two subtleties:

- **Cute pre-empts cycle completion.** When the user taps on the fourth idle
  of an ambient variation, the cycle would normally end and we'd reverse to
  anchor. The counter check skips its `transitionRequested` set when a cute
  branch is pending so the user still gets cute. After cute returns, the
  counter has rolled over to 0 and a fresh four-cycle begins.
- **Pending event during reverse.** If a pending full event exists when the
  reverse transition starts, that event's forward transition is preloaded as
  the next source. In normal interaction flow this branch is unreachable:
  request rules refuse to reserve an event while another event is active, and
  the `isTransitioning` guard blocks requests during the reverse transition.
  The branch exists as defense in depth, parallel to the close-up-over-DWZ
  priority in `takePendingVariationEvent()`.

## Interaction Trigger Map

Stage-tap triggers (route to close-up or cute branch depending on phase — see
the Phase Table):
- Stage click outside forms, bucket UI, and modals
- Stage touch outside forms, bucket UI, and modals
- Generic key press outside form fields, bucket UI, and modals

DWZ triggers:
- Toggle age estimator
- Fill age estimate
- Submit current/death age
- Open deck
- Deck skip/want/done actions
- Open a decade bucket drawer
- Claim an item from a bucket drawer

Esc closes modals and does not trigger animation events.

## Invariants

- Keep ambient, close-up, DWZ, and cute-branch video lists separate.
- The cute-branch list is keyed by ambient variation `id`, not by a counter.
- Do not call `playVideo()` directly from UI handlers.
- UI handlers should only request events by setting state.
- Ignore requests during transition clips, including both halves of a cute
  branch.
- Use `prefetchVariation()` whenever reserving a user-triggered close-up or
  DWZ event. For the cute branch, warm the pair on entry to each ambient idle
  phase rather than at reservation time, so the first tap is responsive.
- The cute branch never reaches the anchor; on return it resumes the same
  ambient variation's idle. Do not introduce code paths that take it to
  anchor without an explicit design change.
- If adding a new event family, add a pending slot, index, request function,
  event type string, and `takePendingVariationEvent()` branch.
