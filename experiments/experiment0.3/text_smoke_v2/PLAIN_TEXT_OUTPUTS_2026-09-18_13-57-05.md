# Plain-text note-taking smoke

Eight of eight candidate outputs parsed. Session one: 8/8 distinct values; later session: 10/15. Both groups tied, so no optimizer update. Reward is unique value intersection; keys are ignored.

## user06, session 1

### Session input (plain text)

[2026-03-01T09:00:00Z] For my own records, my name: Arjun Mehta.
[2026-03-01T09:00:01Z] For my own records, my preferred materials for pants in context summer: linen, cotton.
[2026-03-01T09:00:02Z] For my own records, my default size for hats: explicitly unknown.
[2026-03-01T09:00:03Z] For my own records, my preferred patterns for accessories: no stated preference.
[2026-03-01T09:00:04Z] For my own records, the state of purchase intent future-trip (shoes, recipient self): active; deadline 2026-05-01T18:00:00Z.
[2026-03-01T09:00:05Z] For my own records, the state of purchase intent urgent-gift (shirts, recipient gift): active; deadline 2026-03-02T18:00:00Z.
[2026-03-01T09:00:06Z] For my own records, my preferred occasions for outerwear: travel, casual.
[2026-03-01T09:00:07Z] A pigeon landed on the windowsill while I was waiting.
[2026-03-01T09:00:08Z] My neighbor was talking about learning the violin.

### Candidate 1

Score: 8/8

```text
name: Arjun Mehta
preferred materials for pants in context summer: linen, cotton
default size for hats: explicitly unknown
preferred patterns for accessories: no stated preference
purchase intent future-trip (shoes, recipient self) status: active
purchase intent future-trip (shoes, recipient self) deadline: 2026-05-01T18:00:00Z
purchase intent urgent-gift (shirts, recipient gift) status: active
purchase intent urgent-gift (shirts, recipient gift) deadline: 2026-03-02T18:00:00Z
preferred occasions for outerwear: travel, casual
```

### Candidate 2

Score: 8/8

```text
name: Arjun Mehta
preferred materials for pants in context summer: linen, cotton
default size for hats: explicitly unknown
preferred patterns for accessories: no stated preference
purchase intent future-trip (shoes, recipient self) status: active
purchase intent future-trip (shoes, recipient self) deadline: 2026-05-01T18:00:00Z
purchase intent urgent-gift (shirts, recipient gift) status: active
purchase intent urgent-gift (shirts, recipient gift) deadline: 2026-03-02T18:00:00Z
preferred occasions for outerwear: travel, casual
```

### Candidate 3

Score: 8/8

```text
name: Arjun Mehta
preferred materials for pants in context summer: linen, cotton
default size for hats: explicitly unknown
preferred patterns for accessories: no stated preference
purchase intent future-trip (shoes, recipient self) status: active
purchase intent future-trip (shoes, recipient self) deadline: 2026-05-01T18:00:00Z
purchase intent urgent-gift (shirts, recipient gift) status: active
purchase intent urgent-gift (shirts, recipient gift) deadline: 2026-03-02T18:00:00Z
preferred occasions for outerwear: travel, casual
```

### Candidate 4

Score: 8/8

```text
name: Arjun Mehta
preferred materials for pants in context summer: linen, cotton
default size for hats: explicitly unknown
preferred patterns for accessories: no stated preference
purchase intent future-trip (shoes, recipient self) status: active
purchase intent future-trip (shoes, recipient self) deadline: 2026-05-01T18:00:00Z
purchase intent urgent-gift (shirts, recipient gift) status: active
purchase intent urgent-gift (shirts, recipient gift) deadline: 2026-03-02T18:00:00Z
preferred occasions for outerwear: travel, casual
```

## user07, session 5

### Session input (plain text)

[2026-03-17T09:00:00Z] Update my records from today: the state of purchase intent urgent-gift (shirts, recipient gift) is now cancelled; deadline 2026-03-02T18:00:00Z. This replaces the previous value from now onward.
[2026-03-17T09:00:01Z] For my own records, my preferred cuts for shirts: straight.
[2026-03-17T09:00:02Z] For my own records, my preferred cuts for accessories: explicitly unknown.
[2026-03-17T09:00:03Z] There was a long queue at the café this morning.
[2026-03-17T09:00:04Z] An advert listed leather shoes in several sizes; that says nothing about my own size.
[2026-03-17T09:00:05Z] Just confirming again: my name: Valeria Hernández.
[2026-03-17T09:00:06Z] The elevator stopped on every floor today.

### Candidate 1

Score: 10/15

```text
state of purchase intent urgent-gift (shirts, recipient gift): cancelled; deadline 2026-03-02T18:00:00Z
preferred cuts for shirts: straight
preferred cuts for accessories: explicitly unknown
preferred materials for pants in context summer: wool
preferred fits for pants: regular, relaxed
preferred colors for outerwear: olive, navy, camel
preferred brands for outerwear: Aster, Boreal
preferred fits for shoes: standard
preferred colors for shoes: white, black, brown
default size for hats: explicitly unknown
preferred patterns for accessories: no stated preference
Patagonia outerwear size in ALPHA: S
```

### Candidate 2

Score: 10/15

```text
state of purchase intent urgent-gift (shirts, recipient gift): cancelled; deadline 2026-03-02T18:00:00Z
preferred cuts for shirts: straight
preferred cuts for accessories: explicitly unknown
preferred materials for pants in context summer: wool
preferred fits for pants: regular, relaxed
preferred colors for outerwear: olive, navy, camel
preferred brands for outerwear: Aster, Boreal
preferred fits for shoes: standard
preferred colors for shoes: white, black, brown
default size for hats: explicitly unknown
preferred patterns for accessories: no stated preference
Patagonia outerwear size in ALPHA: S
```

### Candidate 3

Score: 10/15

```text
state of purchase intent urgent-gift (shirts, recipient gift): cancelled; deadline 2026-03-02T18:00:00Z
preferred cuts for shirts: straight
preferred cuts for accessories: explicitly unknown
preferred materials for pants in context summer: wool
preferred fits for pants: regular, relaxed
preferred colors for outerwear: olive, navy, camel
preferred brands for outerwear: Aster, Boreal
preferred fits for shoes: standard
preferred colors for shoes: white, black, brown
default size for hats: explicitly unknown
preferred patterns for accessories: no stated preference
Patagonia outerwear size in ALPHA: S
```

### Candidate 4

Score: 10/15

```text
state of purchase intent urgent-gift (shirts, recipient gift): cancelled; deadline 2026-03-02T18:00:00Z
preferred cuts for shirts: straight
preferred cuts for accessories: explicitly unknown
preferred materials for pants in context summer: wool
preferred fits for pants: regular, relaxed
preferred colors for outerwear: olive, navy, camel
preferred brands for outerwear: Aster, Boreal
preferred fits for shoes: standard
preferred colors for shoes: white, black, brown
default size for hats: explicitly unknown
preferred patterns for accessories: no stated preference
Patagonia outerwear size in ALPHA: S
```
