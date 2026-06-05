# Layout Design Principles

This document is a design knowledge base for the LLM room planner. It describes
how to think about space, furniture relationships, circulation, and style intent
across all room types. The LLM is the room designer — it interprets these
principles and chooses the furniture program accordingly.

---

## LLM placement protocol

The default pipeline (`PLACEMENT_MODE=llm_refine`) asks the LLM to **place**
furniture, not only select it. Output one ordered `placements[]` list:

1. **placement_order 1** — room anchor (see table). Implied pieces are placed by
   the LLM in subsequent orders.
2. **placement_order 2+** — relative placements (nightstands at bed, chairs at
   table, counter segments at sink, etc.).
3. Each placement includes `center_x_m`, `center_z_m`, `orientation` (0|1).

**Required furniture** (all must appear; everything else optional):

| Room | Required |
|------|----------|
| bedroom | bed, desk, chair, wardrobe, nightstand |
| kitchen | dining table, sink, stove, fridge, dining chair, ≥2 counter segments |
| living_room | sofa, coffee table, TV stand |

| Room | Anchor (order 1) | Implied layout |
|------|------------------|----------------|
| bedroom | bed on west wall | nightstands flank bed; desk + chair on east wall |
| living_room | main sofa on south wall | coffee table in front; TV opposite; accent seating around |
| kitchen | dining table (floats) | chairs around table; order 2 sink on north wall with counter run, stove, fridge |

The IP solver enforces **hard** constraints only: no overlap, wall hugging,
orientation lock, and connectivity for small pieces (chairs, nightstands).
Semantic layout is the LLM's job.

---

## Classical Design Principles

These seven principles guide every layout. The LLM tags each placement with
`composition_role` and `zone`; the solver validates balance/proportion/rhythm
and optimizes lateral balance and focal distances.

| Principle | Application |
|-----------|-------------|
| **Structure** | Anchor first (placement_order 1), then support, accent, decor |
| **Emphasis** | Seating faces focal point; TV/art on focal wall |
| **Balance** | Visual mass distributed left/right of room midline |
| **Proportion** | Coffee table 35–45 cm from sofa; scale accents to anchor |
| **Rhythm** | Paired nightstands/lamps; even spacing along wall runs |
| **Harmony** | Consistent materials/forms across selected models |
| **Unity** | Zones align to room axes and read as one composition |

Surface stacking: table lamps use `on_surface_of` (same center as surface);
rugs use `on_surface_of` under coffee table or sofa.

---

## Universal Principles

These apply to every room, regardless of type or size.

### Anchor First

Every room has a primary anchor — the piece of furniture that defines the room's
function and organizes everything else around it. Identify the anchor before
placing anything else. All other furniture decisions are made in relation to it.

- Living room: the primary seating group
- Bedroom: the bed
- Dining zone: the dining table
- Work zone: the desk or work surface
- Kitchen: the prep and cooking surface

If a room has more than one anchor, it has more than one zone. Each zone should
have its own clear anchor and should relate coherently to the other zones.

### Focal Points

Every room has at least one focal point — a visual terminus that draws the eye
and gives the room orientation. Furniture is arranged to acknowledge the focal
point, not fight it.

Common focal points include: a window with a view, a fireplace, a feature wall,
a television, a piece of artwork, or an architectural element like a bay or
alcove. When a room has no natural focal point, one should be created through
furniture arrangement or surface treatment.

Furniture should face toward the focal point, angle toward it, or frame it.
Furniture placed with its back to the focal point without reason reads as
disorganized.

### Circulation

Every room must have clear, unobstructed paths between:

- The door and the primary activity zone
- The primary activity zone and any secondary zones
- Any zone and its associated storage or support furniture

**Minimum clearances:**
- Primary circulation paths (door to main zone): 90cm clear
- Secondary paths (between furniture within a zone): 60cm clear
- Access to a bed from the side: 60cm minimum on at least one long side,
  ideally both
- Pull-out clearance in front of seating: 45cm minimum
- Chair pull-out clearance at dining or desk: 75cm behind the chair when seated

Furniture must not block door swings. Furniture must not obstruct the primary
path through a room even if it fits spatially.

### Wall Relationships

Furniture relates to walls in predictable ways that reflect design convention
and human comfort.

- Beds are almost always placed against a wall on the head end. A bed floating
  in the middle of a room with no wall relationship reads as unresolved unless
  the room is very large and the layout is intentionally symmetrical.
- Sofas may float (with a console table behind them) or anchor to a wall.
  Floating sofas define space more clearly in open-plan rooms; wall-anchored
  sofas suit smaller or more traditional rooms.
- Desks may face a wall, face a window, or face into the room. Facing a blank
  wall suits focused work; facing a window suits creative or contemplative work.
- Dining tables generally float in the center of their zone, equidistant from
  surrounding walls where possible.
- Storage pieces (wardrobes, bookshelves, sideboards) almost always sit against
  walls. A bookshelf floating in open space without structural or zoning purpose
  reads as misplaced.

### Door and Window Relationships

Doors and windows are fixed constraints that the furniture program must respond to.

**Doors:**
- The door swing arc must remain clear of all furniture.
- Furniture placed immediately beside a door should not block the door's
  operation or the line of sight into the room.
- The primary path from the door to the main activity zone should feel natural
  and unforced.

**Windows:**
- Windows are often focal points and should be treated as such.
- Natural light from windows should reach the primary activity zone where
  possible. Tall furniture placed in front of windows blocks light and is
  generally avoided unless the window is not a primary light source.
- Seating that faces a window benefits from natural light for reading and
  contemplation. Screens (televisions, monitors) should not face a window
  directly, as glare makes them unusable.
- Desks placed beside or angled toward a window benefit from natural light
  without direct screen glare.

### Scale and Density

Furniture should be scaled to the room and to each other.

- A compact room should have a focused furniture program. Every piece should
  earn its place. When in doubt, omit.
- A standard room can support a primary zone and one or two secondary elements.
- A spacious room can support multiple zones, but those zones should still
  relate to one another. Empty space in a large room is not a problem to be
  solved — it is part of the composition.

**Compact:** under approximately 12m²
**Standard:** approximately 12–25m²
**Spacious:** over approximately 25m²

These thresholds are approximate. A long narrow room at 15m² may feel compact.
A square room at 20m² may feel generous. Use spatial feel, not area alone.

Furniture pieces within a zone should be proportionally compatible. A very large
sofa paired with a very small coffee table reads as mismatched. A dining table
sized for eight in a room that comfortably seats four reads as oversized.

### Symmetry and Balance

Symmetry is not required, but balance is. A room feels settled when visual
weight is distributed without obvious imbalance.

- Symmetrical arrangements (matching bedside tables, paired accent chairs)
  read as formal and resolved. They suit bedrooms, traditional living rooms,
  and dining rooms.
- Asymmetrical arrangements can feel more relaxed and contemporary, but require
  careful attention to visual weight. A large piece on one side should be
  balanced by multiple smaller pieces, strong color, or open space on the other.
- Avoid clustering all the visual weight on one side of a room with nothing to
  balance it.

### Zones Within a Room

A zone is a functional grouping of furniture organized around a shared activity.
Zones should feel distinct but related.

- Each zone has an anchor piece.
- Zone boundaries are defined by furniture arrangement, rugs, lighting, or a
  combination. They do not require physical walls.
- Zones should not overlap in a way that compromises the function of either.
- A circulation path between zones reinforces their separation and makes the
  room feel organized.

---

## Living Rooms

Living rooms are organized around social use, rest, and occupation. The primary
function is seating and the activities that surround it.

### Primary Zone: Seating

The seating group is the anchor. It defines the room.

- The primary sofa or seating piece faces the focal point.
- Accent chairs should complete the conversation group, not sit in isolation.
  An accent chair facing no useful target — no other seat, no table, no focal
  point, no view — reads as filler.
- A coffee table or equivalent surface belongs within reach of the primary
  seating. The gap between the sofa front and the coffee table edge should be
  approximately 35–45cm — close enough to use, far enough to pass.
- Side tables belong within arm's reach of seating that has no access to the
  coffee table.

### Media

If the room includes media viewing:

- The television or media piece anchors to the focal wall or a wall that the
  primary seating naturally faces.
- The distance between the primary seating and the screen should be
  approximately 1.5–2.5 times the screen diagonal for comfortable viewing.
- Media storage (consoles, shelving) should relate to the media piece, not
  scatter across the room.
- Avoid placing a television in front of a primary window.

Standard and spacious living rooms should include secondary zone elements (side
table, accent chair, rug, lamp, bookshelf) so the seating area feels complete;
empty perimeter is not a goal at standard tier.

### Secondary Zones

Larger living rooms may support secondary zones for reading, work, display, or
entry reception. Secondary zones should:

- Have their own anchor and internal logic
- Not compromise the primary seating zone's circulation or visual coherence
- Relate to the primary zone through alignment, orientation, or shared material

### Storage and Display

- Shelving and storage pieces should read as intentional — anchored to a wall,
  scaled to the room, and serving a legible function (books, display, media,
  entry storage).
- A shelf placed without relationship to the room's activity or circulation
  reads as afterthought.
- Display pieces (artwork, sculpture, plants) should reinforce the room's focal
  moments, not compete with them.

### Lighting Zones

- Primary ambient lighting serves the whole room.
- Task lighting should serve seating, reading, or work moments.
- Accent lighting should reinforce display or focal moments.
- Floor lamps belong beside seating. Table lamps belong on surfaces within a
  zone. Overhead pendants should relate to the zone beneath them.

---

## Bedrooms

Bedrooms are organized around sleeping, dressing, and personal storage. The
atmosphere should support rest.

### Primary Zone: Bed

The bed anchors the room. Everything else is secondary.

- The bed head sits against a wall. The preferred wall is typically opposite or
  perpendicular to the door, giving the occupant a clear sightline to the
  entrance — a deeply instinctive preference.
- The bed should not be placed directly under a window unless no alternative
  exists. A window above the head position causes draft, glare, and light
  interruption during sleep.
- Both sides of the bed should ideally have 60cm of clear passage. In compact
  rooms, one side may reduce to 45cm minimum.
- The foot of the bed should have at least 90cm of clearance to the opposite
  wall or furniture.

### Bedside Zone

- Bedside tables, nightstands, or equivalent surfaces belong on one or both
  sides of the bed head.
- They should be at approximately mattress height for comfortable reach from
  a lying position.
- Bedside lighting (table lamps, sconces, or pendants) belongs at the bedside
  zone.
- Matched pairs of bedside tables read as formal and symmetrical. Unmatched
  pairs or single-sided arrangements read as more casual or space-constrained.

### Storage Zone

- Wardrobes and dressers constitute the clothing storage zone. They should
  read as a coherent group, not scattered around the room.
- Wardrobes typically anchor to walls away from the bed and away from the
  primary window.
- A wardrobe placed across from the foot of the bed is common and functional,
  provided 90cm of clear passage remains.
- Dressers serve as secondary storage and may also hold a mirror. A dresser
  with mirror can double as a vanity.

### Secondary Zones

In standard and spacious bedrooms, secondary zones may include:

- **Reading zone:** An armchair or chaise, with a side table and floor lamp,
  placed near a window or in a corner with good light.
- **Vanity zone:** A dressing table, mirror, and stool, placed near natural
  light where possible.
- **Work zone:** A desk and chair, placed away from the bed. Work furniture in
  a bedroom should not dominate the room or visually compete with the sleep
  zone. The desk should not face the bed.
- **End-of-bed zone:** A bench or ottoman at the foot of the bed, within the
  foot clearance, adds a dressing and layering moment without consuming
  additional floor area.

Compact bedrooms should prioritize the bed and essential storage. Secondary
zones are added only when they do not compromise sleep function or circulation.

---

## Dining Zones

Dining zones are organized around a table-and-seating group. They may be
standalone rooms or part of an open-plan layout.

### Table Placement

- The dining table anchors the zone, ideally centered within its allocated
  floor area.
- The table should have at least 90cm of clearance on all sides to allow chairs
  to be pulled out and occupants to circulate.
- In open-plan layouts, the dining zone should be clearly delineated from
  adjacent living or kitchen zones through furniture arrangement, lighting, or
  a rug.

### Seating

- Dining chairs should be scaled to the table height and depth. A chair seat
  should sit approximately 25–30cm below the table surface.
- The number of chairs should match the table's seating capacity. Overcrowding
  a table with more chairs than it can comfortably seat reads as poorly
  considered.
- Chair pull-out clearance behind each place setting should be 75cm from the
  table edge to any wall or fixed furniture.

### Support Furniture

- A sideboard, buffet, or console along a nearby wall provides storage and
  serving surface. It should relate to the dining table zone, not sit in
  isolation across the room.
- Display or storage pieces near the dining zone should support dining function
  (tableware, linens, glassware) or frame the zone through display.

### Lighting

- A pendant or chandelier centered over the dining table reinforces the zone
  and defines the activity below it.
- The bottom of the pendant should hang approximately 75–85cm above the table
  surface.

---

## Work Zones

Work zones are organized around a primary work surface and the activities that
support it.

### Desk Placement

- The desk anchors the zone. It should face away from high-traffic paths that
  would cause visual distraction.
- Preferred orientations: facing a wall (focus), facing a window from the side
  (natural light without glare), or facing into the room (suited to
  collaborative or supervisory work).
- Avoid placing a screen directly facing a window.

### Chair and Clearance

- The work chair requires 75cm of pull-out clearance behind the seat when
  occupied.
- Adjacent furniture should not encroach on this clearance zone.

### Support and Storage

- A desk benefits from nearby storage: shelving, a filing cabinet, or a
  credenza. Storage placed behind or beside the desk reads as intentional.
  Storage placed across the room requires standing to access and reads as
  disconnected.
- Task lighting at the desk is essential. A desk lamp or directed overhead
  light should illuminate the work surface without casting glare on a screen.

---

## Kitchens

Kitchens are organized around the work triangle: the relationship between the
cooking surface, the sink, and the refrigerator. Layout efficiency is the
primary design driver.

### Catalog-driven counter runs

When using the Kenney furniture kit, prefer modular counter pieces (`kitchenBarEnd`,
`kitchenBar`, `kitchenCabinet`, `kitchenStove`, `kitchenSink`) in a single continuous
run along one wall—not one oversized block. The IP solver enforces an `adjacent_chain`
on that wall so segments touch in order; the refrigerator should sit on the same wall
or adjacent to the end of the run.

### Work Triangle

- The total perimeter of the work triangle (stove to sink to refrigerator)
  should ideally fall between 4m and 9m. Under 4m feels cramped; over 9m
  creates unnecessary movement.
- No leg of the triangle should be interrupted by a primary circulation path.

### Zones

- **Prep zone:** Counter surface adjacent to the cooking surface or sink.
  The primary work zone.
- **Cooking zone:** The stove or cooktop, with clearance above for ventilation
  and space beside it for landing surfaces.
- **Cleaning zone:** The sink, with counter surface on at least one side for
  drying or staging.
- **Storage zone:** Pantry, cabinets, and refrigerator, grouped to minimize
  retrieval distance from the prep zone.

### Clearances

- A single-run kitchen aisle should be at least 100cm wide.
- A galley kitchen with parallel runs should have at least 120cm between
  facing surfaces.
- If two people regularly cook together, 150cm between facing surfaces is
  preferable.

### Dining at the Kitchen

If the kitchen includes an island or peninsula with seating:

- Bar stools require 30–35cm of counter overhang from the knee to the stool
  front.
- Stool spacing should allow 60cm per seat measured center to center.
- Island seating should not obstruct the work triangle.

---

## Hallways and Entry Zones

Entry zones set the tone for the rest of the space. They should feel resolved,
even when small.

### Function

An entry zone should support:
- A place to put things down on arrival (table, shelf, or hook)
- A place to sit for shoes where space allows
- A place to hang outerwear

### Clearances

- A hallway minimum clear width is 90cm. This allows one person to pass
  comfortably with a bag or coat.
- 120cm allows two people to pass. This should be the target for shared or
  primary entry halls.
- Furniture in an entry zone should not reduce the clear walking width below
  90cm.

### Visual Resolution

An entry hall benefits from a focal moment at its terminus — a piece of
furniture, artwork, a mirror, or a window. A hall that ends in a blank wall
with no resolution feels institutional.

---

## Multi-Zone Open-Plan Spaces

Open-plan spaces combine two or more functional zones within a single undivided
volume. The design challenge is to make each zone feel coherent while the whole
reads as unified.

### Zone Delineation

- Use furniture arrangement, rugs, lighting, and ceiling treatment to define
  zone boundaries without walls.
- Each zone should have its own anchor and its own lighting moment.
- Zones should be separated by implied circulation paths — a gap between the
  sofa back and the dining table edge, for example.

### Orientation Consistency

- In open-plan spaces, furniture across zones should generally share a
  consistent orientation to the primary axis of the room. Mixed orientations
  that conflict with the room's geometry create visual noise.
- A living zone and dining zone that both orient to the same window wall or
  focal wall read as unified. Zones that orient in conflicting directions
  read as disconnected.

### Scale Consistency

- Furniture across zones should be scaled consistently to the room, not to each
  zone in isolation. A very large sofa group beside a very small dining set
  reads as mismatched even if each is internally proportionate.

---

## Style Intent

Style should inform material, proportion, and detail — not override function.
A well-functioning layout in the wrong style is still a well-functioning layout.
A stylistically coherent layout that fails functionally is not a good design.

### General Principles

- Establish one dominant style intention for the room. Mixing styles is possible
  but requires deliberate editing. Unedited mixing reads as accidental.
- Scale and proportion are more important than finish. A well-proportioned
  piece in an unexpected material often reads better than a correctly finished
  piece in the wrong scale.
- Repetition of material, color, or form creates coherence. Introduce variation
  within a repeated system rather than accumulating unrelated elements.

### Style Reference Points

The LLM may interpret style descriptions including but not limited to:

- **Contemporary / Modern:** Clean lines, low profiles, neutral palette with
  deliberate accent, materials include matte finishes, stone, and metal.
- **Scandinavian:** Warm neutrals, natural wood, simple forms, emphasis on
  light and function over decoration.
- **Mid-Century Modern:** Tapered legs, organic curves, warm wood tones,
  graphic upholstery, emphasis on form.
- **Industrial:** Exposed structure, metal and reclaimed wood, utilitarian
  forms, darker palette.
- **Traditional / Classical:** Symmetry, ornament, upholstered forms, layered
  textiles, richer palette.
- **Japandi:** Intersection of Japanese and Scandinavian sensibility — extreme
  restraint, natural material, considered negative space, very low furniture
  profiles.
- **Eclectic:** Deliberate mixing of periods and styles, unified by color,
  material, or scale consistency.

When a style is specified, the LLM should interpret it through furniture
selection, proportional preference, and material suggestion — not as a rigid
catalogue of permissible objects.
