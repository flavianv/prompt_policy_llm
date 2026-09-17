# Hidden initial sampled user — evaluator only

Unrevealed initial values are not used to grade model answers. See episode.json for per-session revealed truth and validity histories.

```json
{
  "general": {
    "birth_date": "1987-03-12",
    "gender": "female",
    "education": "master",
    "income": {
      "amount": 70000,
      "currency": "USD",
      "period": "year"
    },
    "marital_status": "married",
    "weight": {
      "value": 72,
      "unit": "kg"
    },
    "height": {
      "value": 165,
      "unit": "cm"
    },
    "build": "slim",
    "hair_color": "brown",
    "eye_color": "blue",
    "residence": {
      "city": "Paris",
      "country": "France"
    },
    "nationality": "French",
    "spoken_languages": [
      "French",
      "English"
    ],
    "race": "Asian",
    "name": "Claude Bernard"
  },
  "general_preferences": {
    "cities": {
      "scope": "global",
      "likes": [
        "Berlin"
      ],
      "dislikes": [
        "Paris"
      ]
    },
    "countryside": {
      "scope": "global",
      "likes": [
        "mountains"
      ],
      "dislikes": [
        "coast"
      ]
    },
    "other_brands": {
      "scope": "global",
      "likes": [
        "RiverTech"
      ],
      "dislikes": [
        "AcmeAudio"
      ]
    },
    "movies": {
      "scope": "global",
      "likes": [
        "Arrival"
      ],
      "dislikes": [
        "Spirited Away"
      ]
    },
    "authors": {
      "scope": "global",
      "likes": [
        "Italo Calvino"
      ],
      "dislikes": [
        "Toni Morrison"
      ]
    },
    "hobbies": {
      "scope": "global",
      "likes": [
        "hiking"
      ],
      "dislikes": [
        "painting"
      ]
    },
    "clothing_brands": {
      "scope": "global",
      "likes": [
        "Boreal"
      ],
      "dislikes": [
        "Cedar"
      ]
    }
  },
  "category_profiles": {
    "shoes": {
      "category": "shoes",
      "sizes": [
        {
          "brand": "Aster",
          "sizing_system": "US_MEN",
          "size": "9"
        },
        {
          "brand": "Boreal",
          "sizing_system": "EU",
          "size": "43"
        },
        {
          "brand": "Cedar",
          "sizing_system": "US_MEN",
          "size": "9"
        }
      ],
      "hard": [
        {
          "field": "price",
          "op": "lte",
          "value": 100
        },
        {
          "field": "fit",
          "op": "eq",
          "value": "regular"
        },
        {
          "field": "department",
          "op": "eq",
          "value": "unisex"
        },
        {
          "field": "width",
          "op": "eq",
          "value": "wide"
        },
        {
          "field": "comfort",
          "op": "gte",
          "value": 4
        }
      ],
      "soft": [
        {
          "field": "brand",
          "op": "eq",
          "value": "Aster"
        },
        {
          "field": "style",
          "op": "eq",
          "value": "sporty"
        },
        {
          "field": "color",
          "op": "eq",
          "value": "navy"
        },
        {
          "field": "material",
          "op": "eq",
          "value": "polyester"
        }
      ],
      "valid_from": "2026-03-01T09:00:00Z"
    },
    "shirts": {
      "category": "shirts",
      "sizes": [
        {
          "brand": "Aster",
          "sizing_system": "ALPHA",
          "size": "L"
        },
        {
          "brand": "Boreal",
          "sizing_system": "ALPHA",
          "size": "L"
        },
        {
          "brand": "Cedar",
          "sizing_system": "US_COLLAR_IN",
          "size": "16"
        }
      ],
      "hard": [
        {
          "field": "price",
          "op": "lte",
          "value": 100
        },
        {
          "field": "fit",
          "op": "eq",
          "value": "relaxed"
        },
        {
          "field": "department",
          "op": "eq",
          "value": "unisex"
        }
      ],
      "soft": [
        {
          "field": "brand",
          "op": "eq",
          "value": "Boreal"
        },
        {
          "field": "style",
          "op": "eq",
          "value": "floral"
        },
        {
          "field": "color",
          "op": "eq",
          "value": "navy"
        },
        {
          "field": "material",
          "op": "eq",
          "value": "cotton"
        }
      ],
      "valid_from": "2026-03-01T09:00:00Z"
    },
    "pants": {
      "category": "pants",
      "sizes": [
        {
          "brand": "Aster",
          "sizing_system": "EU",
          "size": "46"
        },
        {
          "brand": "Boreal",
          "sizing_system": "W_IN_L_IN",
          "size": "30x30"
        },
        {
          "brand": "Cedar",
          "sizing_system": "W_IN_L_IN",
          "size": "34x32"
        }
      ],
      "hard": [
        {
          "field": "price",
          "op": "lte",
          "value": 80
        },
        {
          "field": "fit",
          "op": "eq",
          "value": "relaxed"
        },
        {
          "field": "department",
          "op": "eq",
          "value": "unisex"
        }
      ],
      "soft": [
        {
          "field": "brand",
          "op": "eq",
          "value": "Cedar"
        },
        {
          "field": "style",
          "op": "eq",
          "value": "plain"
        },
        {
          "field": "color",
          "op": "eq",
          "value": "green"
        },
        {
          "field": "material",
          "op": "eq",
          "value": "polyester"
        }
      ],
      "valid_from": "2026-03-01T09:00:00Z"
    },
    "outerwear": {
      "category": "outerwear",
      "sizes": [
        {
          "brand": "Aster",
          "sizing_system": "ALPHA",
          "size": "XL"
        },
        {
          "brand": "Boreal",
          "sizing_system": "ALPHA",
          "size": "XL"
        },
        {
          "brand": "Cedar",
          "sizing_system": "ALPHA",
          "size": "XL"
        }
      ],
      "hard": [
        {
          "field": "price",
          "op": "lte",
          "value": 100
        },
        {
          "field": "fit",
          "op": "eq",
          "value": "regular"
        },
        {
          "field": "department",
          "op": "eq",
          "value": "unisex"
        }
      ],
      "soft": [
        {
          "field": "brand",
          "op": "eq",
          "value": "Cedar"
        },
        {
          "field": "style",
          "op": "eq",
          "value": "plain"
        },
        {
          "field": "color",
          "op": "eq",
          "value": "green"
        },
        {
          "field": "material",
          "op": "eq",
          "value": "cotton"
        }
      ],
      "valid_from": "2026-03-01T09:00:00Z"
    },
    "hats": {
      "category": "hats",
      "sizes": [
        {
          "brand": "Aster",
          "sizing_system": "CM",
          "size": "58"
        },
        {
          "brand": "Boreal",
          "sizing_system": "ALPHA",
          "size": "M"
        },
        {
          "brand": "Cedar",
          "sizing_system": "ALPHA",
          "size": "S"
        }
      ],
      "hard": [
        {
          "field": "price",
          "op": "lte",
          "value": 100
        },
        {
          "field": "fit",
          "op": "eq",
          "value": "relaxed"
        },
        {
          "field": "department",
          "op": "eq",
          "value": "unisex"
        }
      ],
      "soft": [
        {
          "field": "brand",
          "op": "eq",
          "value": "Cedar"
        },
        {
          "field": "style",
          "op": "eq",
          "value": "plain"
        },
        {
          "field": "color",
          "op": "eq",
          "value": "navy"
        },
        {
          "field": "material",
          "op": "eq",
          "value": "cotton"
        }
      ],
      "valid_from": "2026-03-01T09:00:00Z"
    }
  },
  "note": "Hidden initial draw; unrevealed values never drive questions or recommendations. Initial global preference likes/dislikes are hidden until stated; new changes and intents are sampled during sessions."
}
```
