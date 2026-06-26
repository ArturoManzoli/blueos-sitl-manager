--[[
    SITL Manager - true teleport helper for BlueOS

    BlueOS always starts SITL at the hardcoded default home (Florianópolis), because
    ArduPilot Manager passes a fixed `--home` argument. That argument wins over the
    SIM_OPOS_* parameters, so the only way to relocate the *simulated GPS* (rather than
    just the EKF origin) after boot is to reposition the simulated vehicle from a script.

    This script reads the desired position from the standard SIM_OPOS_* parameters and
    calls sim:set_pose() to move the vehicle there. The SITL Manager extension writes
    SIM_OPOS_LAT / SIM_OPOS_LNG / SIM_OPOS_ALT / SIM_OPOS_HDG over MAVLink, then this
    script applies them at runtime.

    Requirements:
      - A recent ArduPilot SITL build that exposes the sim:set_pose() binding.
      - Scripting enabled: set SCR_ENABLE = 1 and reboot the autopilot.
      - Place this file in the autopilot's `scripts/` directory (the SITL working
        directory, e.g. /root/.config/ardupilot-manager/firmware/scripts inside the
        BlueOS core container) and restart the autopilot.

    Note: sim:set_pose() is SITL-only and is ignored on real hardware.
--]]

local UPDATE_INTERVAL_MS = 1000

local function update()
    if not ahrs:initialised() then
        return update, UPDATE_INTERVAL_MS
    end

    local target_lat = param:get('SIM_OPOS_LAT')
    local target_lng = param:get('SIM_OPOS_LNG')
    local target_alt = param:get('SIM_OPOS_ALT')
    local target_hdg = param:get('SIM_OPOS_HDG') or 0

    if target_lat == nil or target_lng == nil then
        return update, UPDATE_INTERVAL_MS
    end

    local destination = Location()
    destination:lat(math.floor(target_lat * 1e7))
    destination:lng(math.floor(target_lng * 1e7))
    destination:alt(math.floor((target_alt or 0) * 100))

    local attitude = Quaternion()
    attitude:from_euler(0, 0, math.rad(target_hdg))

    local velocity = Vector3f()
    local gyro = Vector3f()

    sim:set_pose(0, destination, attitude, velocity, gyro)
    gcs:send_text(6, string.format("SITL Manager: teleported to %.6f, %.6f", target_lat, target_lng))

    -- Run once after the parameters are present; remove the next two lines to keep
    -- continuously pinning the vehicle to the configured position.
    return
end

return update, UPDATE_INTERVAL_MS
