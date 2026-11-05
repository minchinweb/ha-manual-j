# Someday

Ideas for Manual J that aren't planned yet. Each says what it would do, what
it would need, and what stands in the way. Moving one into the work means
writing it up as a spec first.

## Manual T: the registers

ACCA's Manual T (*Air Distribution Basics for Residential and Small
Commercial Buildings*) picks the supply registers and return grilles, after
Manual D has given each run its airflow. Manual D gets the air to the room;
Manual T is about whether it mixes once it's there. It checks:

- **Throw**: how far the jet carries before it slows to a terminal velocity
  (commonly 50 fpm). It should reach most of the way across the room, towards
  the outside wall or window it is meant to wash, without hitting the far
  wall hard.
- **Spread and drop**: how wide the jet fans out, and, for a ceiling or high
  wall outlet, how far it falls before it reaches the people in the room.
- **Face velocity and noise**: the air speed through the register's face,
  which sets how loud it is. Too fast is noisy; too slow throws too short.
- **Placement**: a register under or near the window or outside wall, where
  the load is, and a return path out of the room (a grille, or the undercut
  of a door).

### What it would add

A **Registers** card on the HVAC design tab: for each register, its airflow
(from Manual D), its face velocity, the distance it needs to throw (from its
outlet position to the room's far side, along its jet), and a verdict like
Manual S's (OK, too fast, too short). It would flag a room whose register is
far from its outside walls, and a room with no return path.

### What it would need

- **From House Structure**, more on each register part: the kind of outlet
  (floor, low wall, high wall, ceiling), its pattern (one-way, two-way,
  four-way, round), its face size, and the way it blows. The outlet position
  (`at_x`, `at_y`, `at_z`) and the free area are there already, and so are
  the room's size and its outside walls.
- **Return grilles**, or a door undercut per room, which House Structure
  doesn't have as parts.
- **The register's performance**: throw, spread and drop at a given airflow
  come from the maker's tables, which differ widely between products. Without
  them, a generic table by outlet kind and face velocity would have to stand
  in, and the results would be rough.

### What stands in the way

The performance data. A generic table is easy to get wrong, and the
answer is only as good as it. A first version could check what doesn't need
it: face velocity against a noise limit, and whether each register sits by an
outside wall of its room. It would add throw only once a register's own data
can be entered.

### Prior art to look at

The two projects reviewed in `prior-art-eldr.md` and
`prior-art-projects-manual-j.md` stop at Manual D; neither picks registers.
Look for an open implementation of Manual T, or of the register selection in
the ASHRAE Handbook (Fundamentals, the chapter on room air distribution),
before writing one.
