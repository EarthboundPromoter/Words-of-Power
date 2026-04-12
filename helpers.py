# Words of Power — Pure helper functions
# No game imports, no TTS, no global state.
# These can be tested independently of the running game.

import math
import re
from collections import Counter

# ---- Direction & Spatial Helpers ----

def _cardinal_direction(dx, dy):
    """Convert dx, dy offset to cardinal direction string. Screen coords: y+ = south."""
    if dx == 0 and dy == 0:
        return ""
    angle = math.atan2(-dy, dx)
    degrees = math.degrees(angle) % 360
    directions = ["east", "northeast", "north", "northwest", "west", "southwest", "south", "southeast"]
    index = round(degrees / 45) % 8
    return directions[index]

# Maps atan2-based index (E=0,NE=1,N=2,...) to clockwise-from-north (N=0,NE=1,E=2,...)
_ATAN_TO_CW = [2, 1, 0, 7, 6, 5, 4, 3]

def _bearing_index(dx, dy):
    """Convert (dx, dy) to 8-way compass index (0=N, 1=NE, 2=E, ... 7=NW).
    Returns None if dx == dy == 0."""
    if dx == 0 and dy == 0:
        return None
    angle = math.atan2(-dy, dx)
    degrees = math.degrees(angle) % 360
    return _ATAN_TO_CW[round(degrees / 45) % 8]

def _direction_offset(dx, dy):
    """Exact directional offset for wayfinding. Screen coords: x+ = east, y+ = south.
    Examples: '5 south', '3 southeast', '5 south 3 east', 'here'."""
    if dx == 0 and dy == 0:
        return "here"
    adx, ady = abs(dx), abs(dy)
    ew = "east" if dx > 0 else "west" if dx < 0 else ""
    ns = "south" if dy > 0 else "north" if dy < 0 else ""
    if dx == 0:
        return f"{ady} {ns}"
    if dy == 0:
        return f"{adx} {ew}"
    if adx == ady:
        return f"{adx} {ns}{ew}"
    # Off-axis: larger component first
    if ady >= adx:
        return f"{ady} {ns} {adx} {ew}"
    return f"{adx} {ew} {ady} {ns}"

# ---- Text Processing ----

def _pluralize(name):
    """Simple English pluralization for unit names at speech speed."""
    if not name:
        return name
    if name.endswith(('s', 'x', 'z')):
        return name + 'es'
    if name.endswith('ch') or name.endswith('sh'):
        return name + 'es'
    if name.endswith('f'):
        return name[:-1] + 'ves'
    if name.endswith('fe'):
        return name[:-2] + 'ves'
    if name.endswith('y') and len(name) > 1 and name[-2] not in 'aeiouAEIOU':
        return name[:-1] + 'ies'
    return name + 's'

def _clean_desc(text):
    """Strip game markup tags like [9_dark:dark] -> '9 dark' from description text."""
    def _clean_tag(m):
        content = m.group(1)
        if ':' in content:
            content = content.split(':')[0]
        return content.replace('_', ' ')
    return re.sub(r'\[([^\]]*)\]', _clean_tag, text)

def _split_message_for_speech(msg):
    """Split message text into buffer-navigable chunks.
    Keybinding lines and status effects become individual entries.
    Narrative paragraphs stay grouped."""
    chunks = []
    paragraphs = re.split(r'\n\s*\n', msg.strip())

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        lines = [l.strip() for l in para.split('\n') if l.strip()]

        binding_entries = []
        for line in lines:
            # Skip numpad grid visual lines (just digits and spaces)
            if re.match(r'^[\d\s]+$', line):
                continue
            # Numpad layout "4   6  ->" line: extract description
            if '->' in line and re.match(r'^\d', line):
                desc = line.split('->')[-1].strip()
                if desc:
                    binding_entries.append(f"Numpad: {desc}")
                continue
            # Multi-binding lines (3+ spaces between entries)
            parts = re.split(r'\s{3,}', line)
            if len(parts) > 1 and all(':' in p for p in parts if p.strip()):
                for p in parts:
                    p = p.strip()
                    if p:
                        binding_entries.append(p)
            else:
                binding_entries.append(line)

        # Decide: individual entries (keybinding/status block) vs one chunk
        has_colons = sum(1 for e in binding_entries if ':' in e)
        if has_colons >= 2 and len(binding_entries) > 1:
            # Keybinding or status effect block: each entry is a chunk
            chunks.extend(binding_entries)
        else:
            # Narrative paragraph: collapse to one chunk
            chunks.append(' '.join(binding_entries) if binding_entries else para)

    return chunks if len(chunks) > 1 else [msg]

# ---- Spatial Raycast & Terrain Classification ----

def _ray_length(level, x, y, dx, dy):
    """Count walkable tiles from (x,y) stepping by (dx,dy), not counting start tile."""
    length = 0
    cx, cy = x + dx, y + dy
    while 0 <= cx < level.width and 0 <= cy < level.height:
        if not level.tiles[cx][cy].can_walk:
            break
        length += 1
        cx += dx
        cy += dy
    return length

# 8 directions clockwise: label, dx, dy
_RAYCAST_DIRS = [
    ("north", 0, -1),
    ("northeast", 1, -1),
    ("east", 1, 0),
    ("southeast", 1, 1),
    ("south", 0, 1),
    ("southwest", -1, 1),
    ("west", -1, 0),
    ("northwest", -1, -1),
]

def _count_exits(level, x, y):
    """Count cardinal directions with at least 1 walkable neighbor from (x,y)."""
    count = 0
    for dx, dy in [(0, -1), (0, 1), (1, 0), (-1, 0)]:
        nx, ny = x + dx, y + dy
        if 0 <= nx < level.width and 0 <= ny < level.height and level.tiles[nx][ny].can_walk:
            count += 1
    return count

def _check_corridor_end(level, tx, ty, corridor_dx, corridor_dy):
    """Check if corridor terminal tile is a dead end, following through one bend.
    corridor_dx/dy: unit step direction from player toward this terminal tile.
    Returns True if the corridor effectively dead-ends (including via a single bend)."""
    exits = _count_exits(level, tx, ty)
    if exits == 1:
        return True  # Simple dead end
    if exits != 2:
        return False  # 3+ exits = junction, not a dead end
    # Exactly 2 exits: one back toward player, one perpendicular (a bend).
    # Follow the perpendicular direction and check if it dead-ends.
    back_dx, back_dy = -corridor_dx, -corridor_dy
    for dx, dy in [(0, -1), (0, 1), (1, 0), (-1, 0)]:
        if dx == back_dx and dy == back_dy:
            continue
        nx, ny = tx + dx, ty + dy
        if 0 <= nx < level.width and 0 <= ny < level.height and level.tiles[nx][ny].can_walk:
            ray = _ray_length(level, tx, ty, dx, dy)
            if ray < 1:
                continue
            end_x, end_y = tx + dx * ray, ty + dy * ray
            return _count_exits(level, end_x, end_y) == 1
    return False

def _classify_terrain(level, x, y):
    """Classify tile geometry from cardinal raycasts.
    Returns (class_name, axis_label) or (class_name, None).
    class_name: 'corridor', 'junction', 'dead_end', 'bend', 'open'.
    axis_label: corridor axis + dead end terminus info, None otherwise.
    Corridor dead end detection: checks terminal tiles so player knows
    before committing whether a corridor leads nowhere."""
    n = _ray_length(level, x, y, 0, -1)
    s = _ray_length(level, x, y, 0, 1)
    e = _ray_length(level, x, y, 1, 0)
    w = _ray_length(level, x, y, -1, 0)

    # Count open cardinal directions (distance >= 1)
    exits = sum(1 for d in (n, s, e, w) if d >= 1)

    # Corridor: one axis open (combined >= 2), perpendicular both blocked
    # Check terminus tiles for dead ends so player knows before entering
    if n + s >= 2 and e == 0 and w == 0:
        dead_ends = []
        if n >= 1 and _check_corridor_end(level, x, y - n, 0, -1):
            dead_ends.append('north')
        if s >= 1 and _check_corridor_end(level, x, y + s, 0, 1):
            dead_ends.append('south')
        axis = 'north-south'
        if dead_ends:
            axis += ', dead end ' + ' and '.join(dead_ends)
        return ('corridor', axis)
    if e + w >= 2 and n == 0 and s == 0:
        dead_ends = []
        if e >= 1 and _check_corridor_end(level, x + e, y, 1, 0):
            dead_ends.append('east')
        if w >= 1 and _check_corridor_end(level, x - w, y, -1, 0):
            dead_ends.append('west')
        axis = 'east-west'
        if dead_ends:
            axis += ', dead end ' + ' and '.join(dead_ends)
        return ('corridor', axis)

    # Junction: 3+ cardinal exits AND constrained space
    if exits >= 3:
        has_narrow_axis = (e == 0 or w == 0 or n == 0 or s == 0)
        if has_narrow_axis:
            return ('junction', None)
        # Constrained crossroads: 3-4 cardinal exits but diagonal space is
        # mostly blocked (plus-shaped intersections where corridors meet)
        diag_blocked = 0
        for ddx, ddy in [(-1, -1), (1, -1), (-1, 1), (1, 1)]:
            nx, ny = x + ddx, y + ddy
            if not (0 <= nx < level.width and 0 <= ny < level.height and level.tiles[nx][ny].can_walk):
                diag_blocked += 1
        if diag_blocked >= 3:
            return ('junction', None)

    # Count diagonal exits — real movement options the player can take.
    # Must be counted before dead end check: a tile with 1 cardinal exit
    # but diagonal exits is a bend or junction, not a dead end.
    diag_exits = 0
    for _, dx, dy in _RAYCAST_DIRS:
        if abs(dx) == 1 and abs(dy) == 1:  # diagonal direction
            if _ray_length(level, x, y, dx, dy) >= 1:
                diag_exits += 1
    total_exits = exits + diag_exits

    # Dead end: exactly one total exit (cardinal + diagonal)
    if total_exits == 1:
        return ('dead_end', None)

    # Junction: 3+ total movement options in constrained space
    if total_exits >= 3:
        has_narrow_axis = (e == 0 or w == 0 or n == 0 or s == 0)
        if has_narrow_axis:
            return ('junction', None)

    # Bend/turn: exactly 2 total exits (L-shaped corridor turn)
    if total_exits == 2:
        return ('bend', None)

    # Open: room or unconstrained space — the default, silent
    return ('open', None)

_TERRAIN_LABELS = {
    'corridor': lambda axis: f"corridor {axis}",
    'junction': lambda axis: "junction",
    'dead_end': lambda axis: "dead end",
    'bend': lambda axis: "turn",
}

def _scan_corridor_branches(level, px, py, axis):
    """Walk a corridor axis and find perpendicular openings.
    Distinguishes alcoves (1-tile pocket, single exit back to corridor) from
    branches (corridor continues or connects to other terrain).
    Returns list of "[alcove|branch] [perp_dir] [dist] [axis_dir]" strings.
    Ordered: axis-positive direction first (north/east), nearest to furthest,
    then axis-negative (south/west), nearest to furthest."""
    results = []

    def _classify_opening(cx, cy, dx, dy, dist, axis_dir_name):
        """Classify a perpendicular opening as alcove, nook, or branch.
        cx, cy: corridor tile position. dx, dy: perpendicular step.
        Alcove: 1 tile deep, dead end. Nook: multi-tile dead end.
        Branch: connects to other terrain."""
        perp_name = {(1, 0): 'east', (-1, 0): 'west',
                     (0, -1): 'north', (0, 1): 'south'}[(dx, dy)]
        ray = _ray_length(level, cx, cy, dx, dy)
        if ray == 1 and _count_exits(level, cx + dx, cy + dy) == 1:
            results.append(f"alcove {perp_name} {dist} {axis_dir_name}")
        else:
            # Check if the opening dead-ends (nook) or connects somewhere (branch)
            end_x, end_y = cx + dx * ray, cy + dy * ray
            if _count_exits(level, end_x, end_y) == 1:
                results.append(f"nook {perp_name} {dist} {axis_dir_name}")
            elif _check_corridor_end(level, end_x, end_y, dx, dy):
                results.append(f"nook {perp_name} {dist} {axis_dir_name}")
            else:
                results.append(f"branch {perp_name} {dist} {axis_dir_name}")

    if axis.startswith('north-south'):
        for i in range(1, _ray_length(level, px, py, 0, -1) + 1):
            ty = py - i
            if px + 1 < level.width and level.tiles[px + 1][ty].can_walk:
                _classify_opening(px, ty, 1, 0, i, 'north')
            if px - 1 >= 0 and level.tiles[px - 1][ty].can_walk:
                _classify_opening(px, ty, -1, 0, i, 'north')
        for i in range(1, _ray_length(level, px, py, 0, 1) + 1):
            ty = py + i
            if px + 1 < level.width and level.tiles[px + 1][ty].can_walk:
                _classify_opening(px, ty, 1, 0, i, 'south')
            if px - 1 >= 0 and level.tiles[px - 1][ty].can_walk:
                _classify_opening(px, ty, -1, 0, i, 'south')
    elif axis.startswith('east-west'):
        for i in range(1, _ray_length(level, px, py, 1, 0) + 1):
            tx = px + i
            if py - 1 >= 0 and level.tiles[tx][py - 1].can_walk:
                _classify_opening(tx, py, 0, -1, i, 'east')
            if py + 1 < level.height and level.tiles[tx][py + 1].can_walk:
                _classify_opening(tx, py, 0, 1, i, 'east')
        for i in range(1, _ray_length(level, px, py, -1, 0) + 1):
            tx = px - i
            if py - 1 >= 0 and level.tiles[tx][py - 1].can_walk:
                _classify_opening(tx, py, 0, -1, i, 'west')
            if py + 1 < level.height and level.tiles[tx][py + 1].can_walk:
                _classify_opening(tx, py, 0, 1, i, 'west')
    return results

# ---- Deploy Helpers ----

_DEPLOY_CENTER = 16  # Map center for quadrant labels (33x33 grid, 0-indexed)

def _quadrant_label(x, y):
    """Fixed quadrant relative to map center. NE/SE/SW/NW."""
    c = _DEPLOY_CENTER
    if x >= c:
        return "northeast" if y < c else "southeast"
    else:
        return "northwest" if y < c else "southwest"

def _number_deploy_dupes(items):
    """Add ordinal suffix to duplicate names in a deploy cycling list.
    Items are (entity, x, y, name) tuples. Returns new list with
    ' 1', ' 2' etc. appended to names that appear more than once."""
    base_names = [n for _, _, _, n in items]
    counts = Counter(base_names)
    if not any(c > 1 for c in counts.values()):
        return items
    seen = {}
    result = []
    for entity, x, y, n in items:
        if counts[n] > 1:
            seen[n] = seen.get(n, 0) + 1
            result.append((entity, x, y, f"{n} {seen[n]}"))
        else:
            result.append((entity, x, y, n))
    return result
