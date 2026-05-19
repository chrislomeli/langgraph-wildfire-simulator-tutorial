-- Example scenario plan for region 'lpnf-south'. Sparse: only the cells listed
-- here move; every other seeded cell stays static at its seed value.
--   Cell (33,6): simultaneous heat + drying — both cross the ignition-risk
--                thresholds (temp>32, humidity<15) and hold.
--   Cell (7,6):  two-phase temperature ramp — a gentle rise (released), then a
--                later ease-in spike whose start_value is resolved from the
--                cell's value when phase 2 begins (start_value NULL = chain).
insert into public.scenario_cell_plan
    (region, grid_row, grid_column, layer, metric, start_tick, duration_ticks, start_value, target_value, curve, hold_after)
values
    ('lpnf-south', 33, 6, 0, 'temperature_c', 5, 20, 30, 42, 'linear', true),
    ('lpnf-south', 33, 6, 0, 'humidity_pct', 5, 20, 25, 10, 'linear', true),
    ('lpnf-south', 7, 6, 0, 'temperature_c', 0, 10, 28, 31, 'linear', false),
    ('lpnf-south', 7, 6, 0, 'temperature_c', 12, 18, null, 39, 'ease_in', true);
