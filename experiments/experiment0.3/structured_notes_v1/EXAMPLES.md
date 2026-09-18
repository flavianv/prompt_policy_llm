# Evaluator-only structured targets: first / middle / final

Deterministically derived from existing Maya events. These are gold targets, NOT model outputs and NOT policy inputs. No new sessions, wording changes, model calls or training.

One atomic extraction is one unique scoped ORIGINAL profile attribute with its complete typed current value. Lists and composite values count once; intent status and deadline count separately. History is optional metadata and is NOT required for current-field credit. Reward is the raw correct count; correct/target is a diagnostic only.

## Session1

Maximum reward: 9.

Primary target below is the partial original profile. Optional history and execution metadata are in the corresponding evaluator_only/user01/sessionXX.json file.

```json
{
  "category_profiles": [
    {
      "category": "accessories",
      "preferences": {
        "brands": [
          "Baggu",
          "Cuyana"
        ],
        "patterns": []
      }
    },
    {
      "category": "hats",
      "default_size": null
    },
    {
      "category": "pants",
      "scoped_overrides": [
        {
          "context": {
            "subtype": null,
            "season": "summer",
            "occasion": null
          },
          "preferences": {
            "materials": [
              "linen",
              "cotton"
            ]
          }
        }
      ]
    }
  ],
  "purchase_intents": [
    {
      "id": "urgent-gift",
      "category": "shirts",
      "recipient": "gift",
      "status": "active",
      "deadline": "2026-03-02T18:00:00Z"
    },
    {
      "id": "future-trip",
      "category": "shoes",
      "recipient": "self",
      "status": "active",
      "deadline": "2026-05-01T18:00:00Z"
    }
  ],
  "personal": {
    "name": "Maya Okafor"
  }
}
```

## Session5

Maximum reward: 16.

Primary target below is the partial original profile. Optional history and execution metadata are in the corresponding evaluator_only/user01/sessionXX.json file.

```json
{
  "general_preferences": [
    {
      "topic": "shopping",
      "item": "fast fashion",
      "scope": "global",
      "category": null,
      "stance": "dislike"
    }
  ],
  "category_profiles": [
    {
      "category": "accessories",
      "preferences": {
        "brands": [
          "Baggu",
          "Cuyana"
        ],
        "patterns": []
      }
    },
    {
      "category": "hats",
      "default_size": null
    },
    {
      "category": "outerwear",
      "preferences": {
        "styles": [
          "functional",
          "modern"
        ]
      }
    },
    {
      "category": "pants",
      "scoped_overrides": [
        {
          "context": {
            "subtype": null,
            "season": "summer",
            "occasion": null
          },
          "preferences": {
            "materials": [
              "wool"
            ]
          }
        }
      ],
      "preferences": {
        "materials": [
          "cotton"
        ],
        "styles": [
          "minimal",
          "utility"
        ]
      }
    },
    {
      "category": "shirts",
      "preferences": {
        "cuts": [
          "button-down",
          "camp collar"
        ]
      }
    }
  ],
  "purchase_intents": [
    {
      "id": "urgent-gift",
      "category": "shirts",
      "recipient": "gift",
      "status": "completed",
      "deadline": "2026-03-02T18:00:00Z"
    },
    {
      "id": "future-trip",
      "category": "shoes",
      "recipient": "self",
      "status": "active",
      "deadline": "2026-05-01T18:00:00Z"
    }
  ],
  "professional": {
    "income": {
      "amount": 8400,
      "currency": "CAD",
      "period": "month"
    },
    "occupation": "User experience researcher"
  },
  "personal": {
    "name": "Maya Okafor"
  }
}
```

## Session10

Maximum reward: 25.

Primary target below is the partial original profile. Optional history and execution metadata are in the corresponding evaluator_only/user01/sessionXX.json file.

```json
{
  "category_profiles": [
    {
      "category": "shoes",
      "sizes": [
        {
          "brand": "New Balance",
          "sizing_system": "US_WOMEN",
          "size": "9"
        }
      ]
    },
    {
      "category": "accessories",
      "preferences": {
        "brands": [
          "Aster"
        ],
        "patterns": []
      },
      "default_size": {
        "sizing_system": "ONE_SIZE",
        "size": "one-size"
      }
    },
    {
      "category": "hats",
      "default_size": null
    },
    {
      "category": "outerwear",
      "preferences": {
        "colors": [
          "black",
          "olive",
          "camel"
        ],
        "cuts": [
          "parka",
          "trench"
        ],
        "fits": [
          "regular",
          "relaxed"
        ],
        "styles": [
          "functional",
          "modern"
        ]
      }
    },
    {
      "category": "pants",
      "scoped_overrides": [
        {
          "context": {
            "subtype": null,
            "season": "summer",
            "occasion": null
          },
          "preferences": {
            "materials": [
              "wool"
            ]
          }
        }
      ],
      "preferences": {
        "materials": [
          "wool"
        ],
        "occasions": [
          "casual",
          "work"
        ],
        "patterns": [
          "solid"
        ],
        "styles": [
          "minimal",
          "utility"
        ]
      }
    },
    {
      "category": "shirts",
      "preferences": {
        "cuts": [
          "button-down",
          "camp collar"
        ]
      }
    }
  ],
  "general_preferences": [
    {
      "topic": "shopping",
      "item": "fast fashion",
      "scope": "global",
      "category": null,
      "stance": "dislike"
    }
  ],
  "purchase_intents": [
    {
      "id": "urgent-gift",
      "category": "shirts",
      "recipient": "gift",
      "status": "active",
      "deadline": "2026-05-09T09:00:00Z"
    },
    {
      "id": "future-trip",
      "category": "shoes",
      "recipient": "self",
      "status": "active",
      "deadline": "2026-05-01T18:00:00Z",
      "budget": {
        "amount": 180,
        "currency": "CAD"
      }
    }
  ],
  "professional": {
    "income": {
      "amount": 8400,
      "currency": "CAD",
      "period": "month"
    },
    "occupation": "User experience researcher"
  },
  "languages": [
    {
      "language": "English",
      "proficiency": "fluent"
    },
    {
      "language": "Yoruba",
      "proficiency": "intermediate"
    },
    {
      "language": "French",
      "proficiency": "basic"
    }
  ],
  "personal": {
    "name": "Maya Okafor"
  }
}
```
