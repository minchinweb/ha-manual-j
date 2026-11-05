Changelog
=========

.. release:: unreleased

  - :support:`-` The install button and steps use Home Assistant 2026.11's **Marketplace**, which replaced HACS; HACS (before 2026.11) and copying by hand are still described.
  - :feature:`-` Without an outdoor sensor (or with too short a record), the design temperatures come from the **historical weather** at the home location: ten years of hourly temperature and dew point from Open-Meteo's archive, downloaded in the background on setup and kept until the location moves or a year ends. The dew points give the **cooling design humidity**. Edmonton's fixed values are now only the last resort.
  - :feature:`-` The **altitude** is Home Assistant's elevation, not Edmonton's.
  - :feature:`-` **Manual J, S and D**, moved from Home Thermal Lab's Loads tab into an integration of their own, with each manual in its own file (``manual_j.py``, ``manual_s.py``, ``manual_d.py``; ``air.py`` and ``building.py`` for what they share, ``project.py`` to run them together).
  - :feature:`-` The **HVAC design** tab on House Structure's Thermal Lab page, in place of the lab's Loads view.
  - :feature:`-` The **furnace, air conditioner and detached buildings** are read from House Structure's parts, rather than the lab's energy and building sub-entries. With more than one furnace or air conditioner, the first is checked and the others are noted.
  - :feature:`-` Settings of its own: the **outdoor temperature sensor** whose record gives the design temperatures, the **envelope defaults** (moved from the lab's settings), and each detached building's **indoor design temperatures**, by name (moved from the lab's building sub-entry).
  - :feature:`-` Tells House Structure it **needs** wall and roof sizes and room floor areas, so House Structure raises repairs for them only once Manual J is installed.
  - :feature:`-` Reads **Home Thermal Lab's fitted cooling rates** (``hass.data["home_thermal_lab_fitted"]``) when they're there, for the "UA fitted" and "Fitted ÷ calc" columns, and leaves them empty when they aren't.
