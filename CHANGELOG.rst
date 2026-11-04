Changelog
=========

.. release:: unreleased

  - :feature:`-` **Manual J, S and D**, moved from Home Thermal Lab's Loads tab into an integration of their own, with each manual in its own file (``manual_j.py``, ``manual_s.py``, ``manual_d.py``; ``air.py`` and ``building.py`` for what they share, ``project.py`` to run them together).
  - :feature:`-` The **HVAC design** tab on House Structure's Thermal Lab page, in place of the lab's Loads view.
  - :feature:`-` The **furnace, air conditioner and detached buildings** are read from House Structure's parts, rather than the lab's energy and building sub-entries. With more than one furnace or air conditioner, the first is checked and the others are noted.
  - :feature:`-` Settings of its own: the **outdoor temperature sensor** whose record gives the design temperatures, the **envelope defaults** (moved from the lab's settings), and each detached building's **indoor design temperatures**, by name (moved from the lab's building sub-entry).
  - :feature:`-` Tells House Structure it **needs** wall and roof sizes and room floor areas, so House Structure raises repairs for them only once Manual J is installed.
  - :feature:`-` Reads **Home Thermal Lab's fitted cooling rates** (``hass.data["home_thermal_lab_fitted"]``) when they're there, for the "UA fitted" and "Fitted ÷ calc" columns, and leaves them empty when they aren't.
