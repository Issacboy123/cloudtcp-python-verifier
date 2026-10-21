# Cloud TCP Intermediate Format — Field Reference
`tcp-intermediate-format.schema.json`
---

## structure

| key | type | req | notes |
|---|---|---|---|
| `format_version` | `"1.0.0"` | ✓ | always this exact string |
| `site` | object | ✓ | where and what the project is |
| `typical_application` | object | ✓ | closure type and lane config |
| `temporal_context` | object | | snapshot time + conditions (AI features) |
| `observations` | array | | sensor/count readings (AI input) |
| `zones` | array | ✓ | zone segments in station order |
| `elements` | array | ✓ | every device and feature |
| `predictions` | object | | AI model output — queue, delay, risk, recs |

---

## site

| field | type | req | notes |
|---|---|---|---|
| `name` | string | ✓ | project name |
| `project_number` | string | | agency / contract # |
| `source_file` | string | | original filename |
| `source_format` | enum | | `DXF` `SHP` `GeoJSON` `KMZ` `Other` |
| `coordinate_system` | string | ✓ | e.g. `NAD83_2011`, `WGS84` |
| `units` | enum | ✓ | `feet` or `meters` |
| `road_name` | string | ✓ | |
| `highway_number` | string | | e.g. `US-50`, `SR-84` |
| `location_description` | string | | plain-english limits |
| `city` / `county` / `state` | string | `state` ✓ | two-letter state |
| `created_date` | string | | ISO 8601 date |

---

## typical_application

| field | type | req | notes |
|---|---|---|---|
| `type` | enum | ✓ | `lane_closure` `shoulder_closure` `road_closure` `intersection_closure` `multi_lane_closure` `median_crossover` `ramp_closure` `other` |
| `direction` | enum | ✓ | `NB` `SB` `EB` `WB` `BOTH` |
| `posted_speed_mph` | number | ✓ | |
| `work_zone_speed_mph` | number | | if reduced |
| `lanes_total` | integer | ✓ | before closure |
| `lanes_closed` | integer | | |
| `description` | string | | freeform |

---

## temporal_context

Snapshot conditions attached to the observation set. Every field here becomes a feature for the AI model.

| field | type | notes |
|---|---|---|
| `timestamp` | string | ISO 8601 UTC — when observations were taken |
| `day_of_week` | enum | `Mon` `Tue` `Wed` `Thu` `Fri` `Sat` `Sun` |
| `time_of_day_bin` | enum | `overnight` `am_peak` `midday` `pm_peak` `evening` |
| `weather` | enum | `clear` `cloudy` `light_rain` `heavy_rain` `fog` `snow` `ice` |
| `visibility_mi` | number | |
| `nearby_event` | boolean | true if major event (game, concert) within 5 mi |
| `nearby_event_note` | string | e.g. `"Warriors game at Chase Center"` |
| `school_in_session` | boolean | |

---

## observations

Point readings from sensors or manual counts at snapshot time. One entry per detector or count location.

| field | type | req | notes |
|---|---|---|---|
| `obs_id` | string | ✓ | |
| `source` | enum | ✓ | `loop_detector` `radar` `bluetooth` `manual_count` `connected_vehicle` `camera_cv` |
| `station` | number | ✓ | along centerline |
| `zone_id` | string | | which zone this falls in |
| `speed_mph` | number | | observed speed |
| `volume_vph` | number | | vehicles per hour |
| `occupancy_pct` | number | | % time detector occupied (0–100) |
| `headway_sec` | number | | avg time gap between vehicles |
| `queue_length_ft` | number | | observed queue from this station |
| `note` | string | | |

---

## zones

In station order, from first advance warning sign to end of termination.

| field | type | req | notes |
|---|---|---|---|
| `zone_id` | string | ✓ | referenced by elements, observations, predictions |
| `type` | enum | ✓ | see below |
| `start_station` / `end_station` | number | ✓ | |
| `description` | string | | |

**zone types:**

| type | what it is |
|---|---|
| `advance_warning` | signs before anything happens |
| `transition` | taper where lanes merge or shift |
| `upstream_buffer` | gap between taper and work |
| `work` | where people are actually working |
| `downstream_buffer` | gap after work before termination |
| `termination` | end of all devices |

---

## elements

Typed by `type` discriminator. Every element has `element_id`, `type`, optional `zone_id`, optional `source` (CAD traceability: `layer`, `entity`, `handle`, `block`).

### station_offset

Used by signs, arrow boards, flaggers.

| field | notes |
|---|---|
| `station` | distance along centerline from reference point |
| `offset` | perpendicular distance from centerline (magnitude) |
| `side` | `left` `right` `center` — facing increasing station |

### sign

| field | req | notes |
|---|---|---|
| `mutcd_code` | ✓ | e.g. `W20-1`, `R4-7` |
| `legend` | | text on the sign |
| `size_inches` | | e.g. `48x48` |
| `face_direction` | | `NB` `SB` `EB` `WB` |
| `position` | ✓ | station_offset |

### taper

| field | req | notes |
|---|---|---|
| `taper_type` | ✓ | `merge` `shift` `shoulder` `downstream` |
| `start_station` / `end_station` | ✓ | |
| `start_offset` / `end_offset` | ✓ | ft from centerline at each end |
| `lane_width_ft` | | |
| `side` | | `left` or `right` |

### device_line

Longitudinal run of channelizing devices.

| field | req | notes |
|---|---|---|
| `device` | ✓ | `cone` `drum` `vertical_panel` `barrier` `tubular_marker` |
| `start_station` / `start_offset` | ✓ | |
| `end_station` / `end_offset` | ✓ | |
| `spacing_ft` | ✓ | gap between devices |
| `side` | | `left` or `right` |

### arrow_board

| field | req | notes |
|---|---|---|
| `mode` | ✓ | `flashing` `sequential_arrow` `sequential_chevron` `diamond` `double_arrow` |
| `position` | ✓ | station_offset |

### flagger

| field | req | notes |
|---|---|---|
| `position` | ✓ | station_offset |
| `controls` | | `NB` `SB` `EB` `WB` `BOTH` |

---

## predictions

Written by the AI model. Clients treat this as read-only.

| field | type | notes |
|---|---|---|
| `model_version` | string | which model produced this |
| `predicted_at` | string | ISO 8601 UTC |
| `horizon_minutes` | integer | how far ahead — e.g. `15`, `30`, `60` |
| `by_zone` | array | per-zone outputs (see below) |
| `total_delay_sec` | number | average end-to-end corridor delay |
| `max_queue_ft` | number | worst-case queue across all zones |
| `risk_level` | enum | `low` `moderate` `high` `critical` |
| `recommendations` | array | suggested actions (see below) |

### predictions.by_zone

One entry per zone.

| field | notes |
|---|---|
| `zone_id` | |
| `queue_length_ft` | predicted back-of-queue |
| `delay_sec` | predicted avg vehicle delay through zone |
| `throughput_vph` | predicted vehicles per hour |
| `congestion_index` | 0 = free flow → 1 = full stop |
| `confidence` | 0–1 |

### predictions.recommendations

| field | req | notes |
|---|---|---|
| `action` | ✓ | what to do, e.g. `"Extend advance warning zone 500 ft upstream"` |
| `priority` | ✓ | `info` `low` `medium` `high` `urgent` |
| `zone_id` | | affected zone |
| `element_id` | | specific element if applicable |
| `reason` | | why the model flagged this |

---

## example

```json
{
  "format_version": "1.0.0",
  "site": {
    "name": "Main St Repaving",
    "coordinate_system": "NAD83_2011",
    "units": "feet",
    "road_name": "Main Street",
    "state": "CA"
  },
  "typical_application": {
    "type": "lane_closure",
    "direction": "NB",
    "posted_speed_mph": 45,
    "lanes_total": 2,
    "lanes_closed": 1
  },
  "temporal_context": {
    "timestamp": "2026-10-06T17:15:00Z",
    "day_of_week": "Tue",
    "time_of_day_bin": "pm_peak",
    "weather": "clear",
    "nearby_event": false,
    "school_in_session": true
  },
  "observations": [
    {
      "obs_id": "OBS_1",
      "source": "loop_detector",
      "station": 200,
      "zone_id": "Z1",
      "speed_mph": 38,
      "volume_vph": 1100,
      "occupancy_pct": 22
    },
    {
      "obs_id": "OBS_2",
      "source": "radar",
      "station": 600,
      "zone_id": "Z2",
      "speed_mph": 18,
      "volume_vph": 820,
      "queue_length_ft": 340
    }
  ],
  "zones": [
    { "zone_id": "Z1", "type": "advance_warning", "start_station": 0,    "end_station": 500  },
    { "zone_id": "Z2", "type": "transition",       "start_station": 500,  "end_station": 650  },
    { "zone_id": "Z3", "type": "work",             "start_station": 650,  "end_station": 1800 },
    { "zone_id": "Z4", "type": "termination",      "start_station": 1800, "end_station": 1900 }
  ],
  "elements": [
    {
      "element_id": "E1", "type": "sign",
      "mutcd_code": "W20-1", "legend": "ROAD WORK AHEAD",
      "zone_id": "Z1",
      "position": { "station": 50, "offset": 10, "side": "right" }
    },
    {
      "element_id": "E2", "type": "taper", "taper_type": "merge",
      "start_station": 500, "end_station": 650,
      "start_offset": 12, "end_offset": 24,
      "lane_width_ft": 12, "side": "right", "zone_id": "Z2"
    },
    {
      "element_id": "E3", "type": "device_line", "device": "cone",
      "start_station": 500, "start_offset": 12,
      "end_station": 1800, "end_offset": 12,
      "spacing_ft": 40, "side": "right", "zone_id": "Z3"
    },
    {
      "element_id": "E4", "type": "arrow_board", "mode": "sequential_arrow",
      "zone_id": "Z2",
      "position": { "station": 480, "offset": 6, "side": "right" }
    },
    {
      "element_id": "E5", "type": "flagger", "controls": "NB",
      "zone_id": "Z3",
      "position": { "station": 660, "offset": 8, "side": "right" }
    }
  ],
  "predictions": {
    "model_version": "cloudtcp-v0.3.1",
    "predicted_at": "2026-10-06T17:15:02Z",
    "horizon_minutes": 30,
    "total_delay_sec": 94,
    "max_queue_ft": 780,
    "risk_level": "high",
    "by_zone": [
      { "zone_id": "Z1", "queue_length_ft": 0,   "delay_sec": 12,  "throughput_vph": 1050, "congestion_index": 0.18, "confidence": 0.91 },
      { "zone_id": "Z2", "queue_length_ft": 780,  "delay_sec": 68,  "throughput_vph": 820,  "congestion_index": 0.74, "confidence": 0.87 },
      { "zone_id": "Z3", "queue_length_ft": 0,    "delay_sec": 14,  "throughput_vph": 820,  "congestion_index": 0.21, "confidence": 0.89 }
    ],
    "recommendations": [
      {
        "action": "Extend advance warning zone 500 ft upstream",
        "zone_id": "Z1",
        "priority": "high",
        "reason": "Queue predicted to reach end of advance warning zone within 30 min during pm peak."
      },
      {
        "action": "Reduce taper spacing — add cones every 20 ft instead of 40 ft",
        "element_id": "E3",
        "priority": "medium",
        "reason": "High lateral merge conflict probability at current spacing given observed approach speed."
      }
    ]
  }
}
```
