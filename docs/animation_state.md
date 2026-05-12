# Animation State Transitions

Reference for the video state machine in `index.html`. Read this before
changing interaction behavior or adding another variation set.

## Event Families

There are three kinds of variation playback:

1. Ambient variations
   - Source: `successfulVariations`
   - Videos: legacy `img_0001` through `img_0018`
   - Trigger: automatic after the anchor has completed an idle cycle
   - User interaction does not directly request these anymore

2. Close-up events
   - Source: `closeupVariationVideos`
   - Videos: `succubus_closeup_v01` through `succubus_closeup_v10`
   - Trigger: generic stage click, touch, or key press
   - One pending close-up slot only

3. DWZ events
   - Source: `dwzVariationVideos`
   - Videos: `succubus_dwz_v01` through `succubus_dwz_v06`
   - Trigger: age estimator and bucket-list interactions
   - One pending DWZ slot only

All three families use the same clip shape:

```text
anchor idle(s)
  -> anchor_to_variation_8s
  -> variation idle clips
  -> variation_to_anchor_4s
  -> anchor idle(s)
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

`activeVariationEventType`
: Empty string for ambient events. Set to `closeup` or `dwz` only while that
event is in its variation-idle phase. This lets repeated interactions exit the
current event instead of queueing the next one.

`transitionRequested`
: Asks the current idle loop to end and move to the next transition.

`isTransitioning`
: True while a forward or reverse transition clip is playing. Interaction
requests are ignored during this period.

`idleClipQueues` and `idleClipPlayCounts`
: Shuffle and count idle clips per anchor/variation id. Each id plays a
four-idle cycle before automatically returning.

## Request Rules

### Close-up request

`requestCloseupVariation()` is called by stage click, touch, and generic key
press.

```text
if transition clip is active:
  ignore
else if current event type is closeup:
  request return to anchor
else if any event is active or pending:
  ignore
else:
  reserve next close-up
  prefetch it
  request current idle to end
```

### DWZ request

`requestDwzVariation()` is called by age and bucket-list UI actions.

```text
if transition clip is active:
  ignore
else if current event type is dwz:
  request return to anchor
else if any event is active or pending:
  ignore
else:
  reserve next DWZ event
  prefetch it
  request current idle to end
```

Close-up and DWZ requests intentionally do not stack. At most one event can be
pending, and interactions during another event family are ignored.

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
event families.

```text
prefetch current variation and next ambient transition
play anchor -> variation transition
set activeVariationEventType to eventType

while no return requested and no pending event:
  play shuffled idle clips for this variation
  after four idles, request return to anchor

clear activeVariationEventType
play variation -> anchor transition
```

If a pending event appears while returning to anchor, the reverse transition
preloads that event's forward transition as the next source.

## Interaction Trigger Map

Close-up triggers:
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

- Keep ambient, close-up, and DWZ video lists separate.
- Do not call `playVideo()` directly from UI handlers.
- UI handlers should only request events by setting state.
- Ignore requests during transition clips.
- Use `prefetchVariation()` whenever reserving a user-triggered event.
- If adding a new event family, add a pending slot, index, request function,
  event type string, and `takePendingVariationEvent()` branch.
