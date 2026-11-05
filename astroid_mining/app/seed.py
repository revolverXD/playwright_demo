"""Seed fleet: the fleet is booted from a known-good state so tests have data.

Ids are the ones used in the fleet documentation (schemaVersion 1.5.0).
"""

import json

from . import auth, clock, db

# Demo accounts. `admin` may change fleet state, `viewer` may only read it.
# The passwords are plain here on purpose: they are the seeded demo login, hashed into the database.
USERS = [
    {"username": "fleet-admin", "password": "regolith-7", "role": "admin", "displayName": "Operations lead"},
    {"username": "site-observer", "password": "stargazer-2", "role": "viewer", "displayName": "Read-only observer"},
]

HEPHAESTUS_7 = {
    "id": "9f1c4c2e-8b7a-4d6f-9a3e-2c5d7e8f1a44",
    "name": "HEPHAESTUS-7",
    "operator": "Helios Resources Ltd.",
    "model": "HR-Mining Relay Mk III",
    "serialNumber": "HRM3-0742",
    "status": "OPERATIONAL",
    "launchDate": "2031-04-18T06:12:00Z",
    "commissionedAt": "2031-05-02T11:40:00Z",
    "designLifeYears": 15,
    "tags": ["asteroid-belt", "ore-transport", "relay", "robot-telemetry-gateway"],
    "orbit": {
        "referenceFrame": "SUN_ECLIPTIC",
        "semiMajorAxisKm": 412500000,
        "eccentricity": 0.0342,
        "inclinationDeg": 5.87,
        "argumentOfPeriapsisDeg": 214.6,
        "longitudeAscendingNodeDeg": 88.1,
        "meanAnomalyAtEpochDeg": 12.44,
        "epoch": "2035-01-01T00:00:00Z",
        "positionKm": [4.09e8, -1.22e7, 4.21e6],
        "velocityKmS": [12.84, 26.11, -1.37],
    },
    "metrics": {
        "collectedAt": "2035-06-11T14:03:27Z",
        "healthScore": 0.94,
        "power": {
            "arrayOutputKw": 118.4,
            "batteryChargePct": 87.2,
            "batteryHealthPct": 93.0,
            "busVoltageV": 100.8,
            "consumptionKw": 74.6,
            "marginKw": 43.8,
        },
        "thermal": {
            "coreTempC": 22.4,
            "radiatorTempC": -12.1,
            "reactorTempC": 41.7,
            "maxAllowedC": 85.0,
            "coolantLoopPressureBar": 3.1,
        },
        "propulsion": {
            "propellantMassKg": 1240.5,
            "propellantRemainingPct": 61.3,
            "deltaVRemainingMs": 2110.0,
            "totalDeltaVUsedMs": 3412.0,
            "engineRuns": 148,
            "lastManeuver": "2035-05-29T02:14:00Z",
        },
        "comms": {
            "signalStrengthDbm": -112.4,
            "downlinkMbps": 480.0,
            "uplinkKbps": 96.0,
            "roundTripLightTimeS": 1372.5,
            "packetLossPct": 0.02,
            "bitErrorRate": 1.2e-9,
            "activeAntenna": "HGA-1",
            "handoverCandidates": ["DSN-CERES", "RELAY-NODE-4"],
        },
        "attitude": {
            "quaternion": [0.7071, 0.0, 0.7071, 0.0],
            "ratesDegS": [0.002, -0.001, 0.0004],
            "sunPointingErrorDeg": 0.42,
            "reactionWheelSpeedsRpm": [2110, -1987, 44],
            "pointingMode": "TRIANGLE_ON_BODY_TRACKING",
            "robotBeamPointingErrorDeg": 0.08,
        },
        "payload": {
            "regolithIntakeTons": 8412.0,
            "refinedOreTons": 1902.7,
            "processingUptimePct": 97.8,
            "crusherRpm": 1450,
            "dustShieldIntegrityPct": 81.0,
        },
        "gateway": {
            "robotSessionsActive": 2,
            "baseSessionsActive": 1,
            "aggregateIngestMbps": 1.42,
            "retainedTelemetryDays": 30,
            "relayQueueDepthMb": 214.0,
            "commandUplinkQueue": 2,
        },
        "anomalies": {
            "openCount": 2,
            "lastFaultCode": "TWB_BEARING_DRIFT",
            "faultHistory": [
                {"code": "TWB_BEARING_DRIFT", "at": "2035-06-09T22:10:00Z", "severity": "MINOR"},
                {"code": "ARRAY_STRING_3_DEGRADED", "at": "2035-03-14T08:33:00Z", "severity": "MAJOR"},
            ],
        },
    },
    "robotics": {
        "role": "RELAY_AND_TRACKING",
        "commandAuthority": {
            "canTelecommandRobots": True,
            "authorityTier": "ROUTINE_ONLY",
            "requiresBaseApprovalFor": ["CUT_BENCH_NEW_ZONE", "TOOL_SWAP", "RETURN_TO_DOCK_OVERRIDE"],
        },
        "beaconSchedule": {"mode": "ON_DEMAND_PLUS_300S_BEACON", "priorityUplink": ["SAFETY", "ESTOP", "TASK_ABORT"]},
        "handover": {"rule": "RELAY_FOLLOWING_LINE_OF_SIGHT", "handoverCooldownS": 600, "lastHandoverAt": "2035-05-30T11:22:00Z"},
    },
    "links": {"upstreamSatelliteIds": ["7e3b1d55-9a48-42c6-b07f-5d1e83c2a694"], "downstreamSatelliteIds": ["4b7d9f01-3c2a-4e8b-9f16-7a2c8d5b6e10"]},
    "metadata": {
        "firmwareVersion": "3.11.2",
        "groundSegment": "CERES-OPS",
        "lastTelemetrySync": "2035-06-11T14:03:27Z",
        "updatedBy": "fleet-orchestrator",
    },
}

RELAY_NODE_4 = {
    "id": "7e3b1d55-9a48-42c6-b07f-5d1e83c2a694",
    "name": "RELAY-NODE-4",
    "operator": "Helios Resources Ltd.",
    "model": "HR-Mining Relay Mk II",
    "serialNumber": "HRM2-0219",
    "status": "OPERATIONAL",
    "commissionedAt": "2029-11-04T09:00:00Z",
    "designLifeYears": 12,
    "tags": ["relay", "backup"],
    "orbit": {"referenceFrame": "SUN_ECLIPTIC", "semiMajorAxisKm": 411900000, "eccentricity": 0.041, "inclinationDeg": 6.2},
    "metrics": {
        "collectedAt": "2035-06-11T14:02:55Z",
        "healthScore": 0.71,
        "power": {"arrayOutputKw": 61.0, "batteryChargePct": 44.0, "consumptionKw": 52.0, "marginKw": 9.0},
        "thermal": {"coreTempC": 31.5, "radiatorTempC": -8.4, "maxAllowedC": 85.0},
        "comms": {"signalStrengthDbm": -131.0, "downlinkMbps": 0.096, "uplinkKbps": 32.0, "roundTripLightTimeS": 85.4},
        "gateway": {"robotSessionsActive": 0, "baseSessionsActive": 1, "relayQueueDepthMb": 980.0},
        "anomalies": {"openCount": 1, "lastFaultCode": "ARRAY_STRING_2_DEGRADED"},
    },
}

DSN_CERES = {
    "id": "4b7d9f01-3c2a-4e8b-9f16-7a2c8d5b6e10",
    "name": "DSN-CERES",
    "operator": "Deep Space Network",
    "model": "Deep Space Relay 40m",
    "serialNumber": "DSN-4011",
    "status": "OPERATIONAL",
    "commissionedAt": "2028-02-20T09:00:00Z",
    "designLifeYears": 30,
    "tags": ["ground-segment", "deep-space-network", "backup"],
    "orbit": {"referenceFrame": "SUN_ECLIPTIC", "semiMajorAxisKm": 2.77e8, "eccentricity": 0.0758},
    "metrics": {
        "collectedAt": "2035-06-11T14:00:00Z",
        "healthScore": 0.99,
        "power": {"arrayOutputKw": 0.0, "gridDrawKw": 420.0, "marginKw": 0.0},
        "thermal": {"coreTempC": 21.0, "maxAllowedC": 60.0},
        "comms": {"signalStrengthDbm": -148.0, "downlinkMbps": 1200.0, "uplinkKbps": 512.0, "roundTripLightTimeS": 1420.0},
        "anomalies": {"openCount": 0},
    },
}

COLD_STANDBY_VESTA = {
    "id": "c2a58e6f-1d47-4b93-8c0a-6f9d2b41e773",
    "name": "VESTA-COLD-1",
    "operator": "Helios Resources Ltd.",
    "model": "HR-Mining Relay Mk I",
    "serialNumber": "HRM1-0031",
    "status": "STANDBY",
    "commissionedAt": "2026-07-15T09:00:00Z",
    "designLifeYears": 20,
    "tags": ["cold-standby"],
    "orbit": {"referenceFrame": "SUN_ECLIPTIC", "semiMajorAxisKm": 353400000, "eccentricity": 0.011},
    "metrics": {
        "collectedAt": "2035-05-01T00:00:00Z",
        "healthScore": 0.83,
        "power": {"arrayOutputKw": 0.0, "batteryChargePct": 96.0},
        "thermal": {"coreTempC": -41.0, "maxAllowedC": 85.0},
        "comms": {"downlinkMbps": 0.0},
        "anomalies": {"openCount": 0},
    },
}

PSYCHE_DRILL_02 = {
    "id": "5c1e9a83-2f64-4b7a-8d21-9e0c7b4f6a52",
    "name": "PSYCHE-DRILL-02",
    "operator": "Helios Resources Ltd.",
    "model": "HAB-Extraction Node Mk II",
    "serialNumber": "HEN2-0117",
    "class": "SURFACE_MINING_BASE",
    "status": "OPERATIONAL",
    "crewed": False,
    "autonomyTier": "L4_SUPERVISED",
    "commissionedAt": "2032-09-30T18:22:00Z",
    "designLifeYears": 25,
    "tags": ["asteroid-surface", "nickel-iron", "robot-fleet-host"],
    "siteRef": {
        "siteId": "a94f2c70-6b18-4d5a-92e3-0c7f4a6d8b21",
        "designation": "PSYCHE-SW-04",
        "anchoredToBodyId": "b6e0c1d4-77a3-4c8e-91f2-0d5a6b3c8e19",
        "hostBody": {
            "provisionalName": "(4124) Orvar-SW",
            "taxonomy": "M-anomalous / Ni-Fe",
            "meanRadiusKm": 12.4,
            "massKg": 4.1e15,
            "surfaceGravityMs2": 0.000148,
            "escapeVelocityMs": 0.061,
            "rotationPeriodH": 8.4,
            "regolithDepthM": 2.8,
            "estimatedNiFeGradePct": 41.7,
            "waterIcePpm": 320,
        },
    },
    "surfaceLocation": {
        "bodyFixedFrame": "BODY_PRINCIPAL_AXES",
        "latitudeDeg": -38.412,
        "longitudeDeg": 271.06,
        "radiusFromCenterKm": 11.94,
        "elevationM": -14.2,
        "anchorPoints": [
            {"anchorId": "AN-01", "penetrationM": 6.5, "holdForceKn": 180.0, "state": "NOMINAL"},
            {"anchorId": "AN-02", "penetrationM": 6.5, "holdForceKn": 174.2, "state": "NOMINAL"},
            {"anchorId": "AN-03", "penetrationM": 5.1, "holdForceKn": 96.7, "state": "DEGRADED"},
        ],
    },
    "metrics": {
        "collectedAt": "2035-06-11T14:03:41Z",
        "healthScore": 0.88,
        "uptimePct30d": 99.1,
        "power": {
            "sourceMix": [
                {"type": "FISSION_RTG", "ratedKw": 220.0, "actualKw": 196.4},
                {"type": "SOLAR_ARRAY", "ratedKw": 340.0, "actualKw": 241.9, "dustFoulingPct": 28.9},
            ],
            "totalGenerationKw": 438.3,
            "consumptionKw": 402.7,
            "peakDemandKw": 511.0,
            "bankChargePct": 71.4,
            "loadShedActive": False,
        },
        "thermal": {
            "coreTempC": 19.8,
            "exteriorTempC": -68.2,
            "sinteringFurnaceTempC": 1385.0,
            "radiatorEfficiencyPct": 82.0,
            "heatRejectionKw": 118.4,
        },
        "structure": {
            "hullPressureBar": 1.01,
            "leakRateBarPerDay": 0.0004,
            "microCrackCount": 14,
            "anchorLoadAsymmetryPct": 6.2,
            "blastShieldIntegrityPct": 73.5,
        },
        "excavation": {
            "activePitCount": 2,
            "drillBitWearPct": 64.0,
            "crusherThroughputTph": 96.5,
            "sintererOutputTph": 41.2,
            "conveyorVibrationMmS": 1.9,
            "dustSuppressionPct": 88.0,
            "inducedSeismicityEvents": 27,
            "maxLocalMagnitude": 0.8,
        },
        "comms": {
            "localMeshNodesOnline": 9,
            "meshCoveragePct": 94.0,
            "robotLinksDropped24h": 3,
            "storeForwardBacklogMb": 1842.0,
            "bufferCapacityMb": 512000.0,
            "ephemerisAgeS": 41.5,
        },
        "computing": {"fleetOrchestratorCpuPct": 44.0, "plannerLatencyMs": 260.0, "modelVersion": "orepath-7.3.1"},
        "inventory": {
            "rawOreOnSiteTons": 18410.0,
            "refinedMetalTons": 6204.5,
            "sparesOnHandPct": 61.0,
            "propellantForTankersKg": 41900.0,
        },
        "anomalies": {
            "openCount": 3,
            "lastFaultCode": "ANCHOR_03_HOLD_LOW",
            "faultHistory": [
                {"code": "ANCHOR_03_HOLD_LOW", "at": "2035-06-10T03:12:00Z", "severity": "MAJOR"},
                {"code": "ARRAY_WING_B_FOULING", "at": "2035-05-21T19:44:00Z", "severity": "MINOR"},
                {"code": "MESH_NODE_07_RETRY", "at": "2035-06-08T11:02:00Z", "severity": "MINOR"},
            ],
        },
    },
    "zones": [
        {
            "zoneId": "0f7c2a91-6d3b-4e28-9c47-58ba1e0d3f66",
            "name": "PIT-1 EAST BENCH",
            "status": "ACTIVE",
            "estimatedTonsReserve": 640000.0,
            "gradeNiFePct": 44.2,
            "excavatedTons": 128400.0,
            "depthM": 14.5,
            "slopeStabilityPct": 88.0,
        },
        {
            "zoneId": "7b3d8c40-2e19-4a76-85fd-1c90a6b2e7d4",
            "name": "PIT-2 SHOULDER",
            "status": "ACTIVE",
            "estimatedTonsReserve": 210000.0,
            "gradeNiFePct": 37.9,
            "excavatedTons": 41050.0,
            "depthM": 6.2,
            "slopeStabilityPct": 71.0,
        },
        {
            "zoneId": "9e4a1b72-5d83-4c06-8f21-73cb0d5e8a11",
            "name": "SURVEY GRID NE",
            "status": "SURVEY",
            "estimatedTonsReserve": None,
            "gradeNiFePct": None,
            "excavatedTons": 0.0,
        },
    ],
    "satelliteLinks": {
        "reportingPolicy": {
            "mode": "STORE_AND_FORWARD",
            "cadenceSeconds": 900,
            "reportSchema": "base.telemetry.report.v1",
            "priorityQueues": ["SAFETY", "FLEET_STATE", "PRODUCTION", "RAW_TELEMETRY"],
            "compress": "zstd-9",
            "ackTimeoutS": 3000,
            "escalateAfterMissedReports": 2,
        },
        "failover": {
            "strategy": "PRIMARY_THEN_SECONDARY_THEN_DIRECT_TO_GROUND",
            "triggerAfterLinkLossS": 1800,
            "degradedReportingWhenNoLink": "SAFETY_AND_FLEET_STATE_ONLY",
        },
    },
    "metadata": {"firmwareVersion": "4.2.0", "groundSegment": "CERES-OPS", "configHash": "sha256:7f1cc40e"},
}

PSYCHE_DRILL_01 = {
    "id": "e70b39a5-2c48-4d1f-9b6a-84fc0e2d7b13",
    "name": "PSYCHE-DRILL-01",
    "operator": "Helios Resources Ltd.",
    "model": "HAB-Extraction Node Mk I",
    "serialNumber": "HEN1-0084",
    "class": "SURFACE_MINING_BASE",
    "status": "OPERATIONAL",
    "crewed": False,
    "autonomyTier": "L3_SUPERVISED",
    "commissionedAt": "2030-03-14T10:00:00Z",
    "designLifeYears": 25,
    "tags": ["asteroid-surface", "nickel-iron"],
    "siteRef": {
        "siteId": "f18c3d92-74ae-4c07-9e5b-3b60d28af144",
        "designation": "PSYCHE-NE-01",
        "anchoredToBodyId": "b6e0c1d4-77a3-4c8e-91f2-0d5a6b3c8e19",
        "hostBody": {
            "provisionalName": "(4124) Orvar-NE",
            "taxonomy": "M-main / Ni-Fe",
            "meanRadiusKm": 12.4,
            "estimatedNiFeGradePct": 33.9,
            "waterIcePpm": 120,
        },
    },
    "metrics": {
        "collectedAt": "2035-06-11T14:01:12Z",
        "healthScore": 0.79,
        "power": {"totalGenerationKw": 288.0, "consumptionKw": 271.0, "bankChargePct": 55.0, "loadShedActive": True},
        "thermal": {"coreTempC": 24.2, "exteriorTempC": -71.0, "sinteringFurnaceTempC": 1310.0},
        "excavation": {"activePitCount": 1, "crusherThroughputTph": 44.0, "sintererOutputTph": 18.4},
        "inventory": {"rawOreOnSiteTons": 7120.0, "refinedMetalTons": 2010.0, "sparesOnHandPct": 34.0},
        "anomalies": {"openCount": 1, "lastFaultCode": "SOLAR_ARRAY_WING_B_FOULING"},
    },
}

SURVEY_GRID_NE = {
    "id": "9b2d4f77-1c6a-4e05-8f3b-6a70d1c4e2b8",
    "name": "PSYCHE-SURVEY-NE",
    "operator": "Helios Resources Ltd.",
    "model": "HAB-Survey Mast Mk I",
    "serialNumber": "HSM1-0009",
    "class": "SURVEY_STATION",
    "status": "OPERATIONAL",
    "crewed": False,
    "autonomyTier": "L5_AUTONOMOUS",
    "commissionedAt": "2034-01-08T16:00:00Z",
    "designLifeYears": 10,
    "tags": ["survey", "assay"],
    "siteRef": {
        "siteId": "0d6b7a48-2f91-4c3d-84ae-91e5f7b0c2d6",
        "designation": "PSYCHE-NE-SURVEY",
        "anchoredToBodyId": "b6e0c1d4-77a3-4c8e-91f2-0d5a6b3c8e19",
        "hostBody": {
            "provisionalName": "(4124) Orvar-NE",
            "taxonomy": "M-main / Ni-Fe",
            "estimatedNiFeGradePct": 28.4,
            "waterIcePpm": 90,
        },
    },
    "metrics": {
        "collectedAt": "2035-06-11T13:55:00Z",
        "healthScore": 0.96,
        "power": {"totalGenerationKw": 4.2, "consumptionKw": 2.1, "bankChargePct": 88.0},
        "thermal": {"coreTempC": 12.0, "exteriorTempC": -74.5},
        "inventory": {"rawOreOnSiteTons": 0.0, "refinedMetalTons": 0.0, "sparesOnHandPct": 90.0},
        "anomalies": {"openCount": 0},
    },
}

ROBOT_TEMPLATE = {
    "status": "OPERATIONAL",
    "mode": "AUTONOMOUS",
    "operator": "Helios Resources Ltd.",
    "tags": [],
    "platform": {
        "driveType": "ROCKER_BOGIE_WHEEL",
        "wheels": 8,
        "powerSource": "RECHARGEABLE_LFP + RTG_TRICKLE",
        "energyCapacityKwh": 96.0,
        "instruments": ["XRF_ASSAY", "LIDAR_SLAM"],
    },
    "metrics": {
        "collectedAt": "2035-06-11T14:03:38Z",
        "healthScore": 0.91,
        "odometryM": 184220.0,
        "operatingHours": 15412.5,
        "mobility": {"speedMs": 0.021, "headingDeg": 138.2, "wheelSlipPct": 4.1, "traversedTodayM": 412.0},
        "power": {
            "batteryPct": 62.4,
            "stateOfHealthPct": 88.0,
            "chargeCycles": 1284,
            "busVoltageV": 51.2,
            "consumptionKw": 18.4,
            "minutesToCritical": 412,
        },
        "thermal": {"coreTempC": 26.1, "gearboxTempC": 48.9, "batteryTempC": 14.2, "minSurvivableC": -95.0},
        "tasking": {"currentTaskId": None, "taskType": None, "progressPct": 0.0, "tonsMoved": 0.0, "throughputTph": 0.0},
        "comms": {"linkQualityPct": 97.0, "meshRssiDbm": -71.0, "uplinkRssiDbm": -128.0, "commandQueueDepth": 0},
        "safety": {"proximityContacts24h": 1, "rsiTrips24h": 0, "estopState": "ARMED"},
        "autonomy": {"plannerVersion": "orepath-7.3.1", "confidencePct": 94.0},
        "anomalies": {"openCount": 0, "faultHistory": []},
    },
    "geofence": {"maxDistanceFromBaseM": 8000.0, "violationAction": "AUTO_RETURN_TO_DOCK"},
    "maintenance": {"serviceIntervalHours": 900, "hoursSinceService": 612.0},
    "metadata": {"firmwareVersion": "9.4.1", "updatedBy": "base-orchestrator"},
}

ROBOTS = [
    {
        "id": "8a2f6d31-5b04-4c97-9a8e-1d6c4f7b20e5",
        "designation": "DOGGE-01",
        "class": "HEAVY_EXCAVATOR",
        "model": "HR-Traverse Digger Mk4",
        "serialNumber": "HTD4-0031",
        "state": "ACTIVE",
        "siteId": "a94f2c70-6b18-4d5a-92e3-0c7f4a6d8b21",
        "baseStationId": "5c1e9a83-2f64-4b7a-8d21-9e0c7b4f6a52",
        "zoneId": "0f7c2a91-6d3b-4e28-9c47-58ba1e0d3f66",
        "batteryPct": 62.4,
        "healthPct": 91.0,
        "task": {"currentTaskId": "c94e1b70-38af-4d15-8f22-6b7d90c4e1a3", "taskType": "CUT_BENCH", "progressPct": 47.0, "tonsMoved": 1974.0, "throughputTph": 41.8},
        "tags": ["pit-duty", "assay-capable"],
    },
    {
        "id": "2d7b48f6-91c3-4a0e-8b57-3e19d6a2c4b8",
        "designation": "DOGGE-04",
        "class": "HEAVY_EXCAVATOR",
        "model": "HR-Traverse Digger Mk4",
        "serialNumber": "HTD4-0044",
        "state": "CHARGING",
        "siteId": "a94f2c70-6b18-4d5a-92e3-0c7f4a6d8b21",
        "baseStationId": "5c1e9a83-2f64-4b7a-8d21-9e0c7b4f6a52",
        "zoneId": None,
        "batteryPct": 34.9,
        "healthPct": 68.2,
        "task": {"currentTaskId": None, "taskType": None, "progressPct": 0.0, "tonsMoved": 0.0, "throughputTph": 0.0},
    },
    {
        "id": "6c9f28b1-0e47-42d3-8a19-b5f7c30d24e6",
        "designation": "EYE-02",
        "class": "SCOUT_SURVEY",
        "model": "HR-Recon Rover Mk2",
        "serialNumber": "HRR2-0102",
        "state": "ACTIVE",
        "siteId": "a94f2c70-6b18-4d5a-92e3-0c7f4a6d8b21",
        "baseStationId": "5c1e9a83-2f64-4b7a-8d21-9e0c7b4f6a52",
        "zoneId": "9e4a1b72-5d83-4c06-8f21-73cb0d5e8a11",
        "batteryPct": 44.2,
        "healthPct": 96.5,
        "task": {"currentTaskId": "e21a7f85-4c06-4b93-a7d8-0f3b6c1e92a4", "taskType": "ASSAY_SWEEP", "progressPct": 12.0, "tonsMoved": 0.0, "throughputTph": 0.0},
    },
    {
        "id": "b41e07c9-8a2d-46f1-93c5-7e0b28af5d13",
        "designation": "MOLE-09",
        "class": "HAULER",
        "model": "HR-Haul Sled Mk3",
        "serialNumber": "HHS3-0209",
        "state": "RETURNING",
        "siteId": "a94f2c70-6b18-4d5a-92e3-0c7f4a6d8b21",
        "baseStationId": "5c1e9a83-2f64-4b7a-8d21-9e0c7b4f6a52",
        "zoneId": "7b3d8c40-2e19-4a76-85fd-1c90a6b2e7d4",
        "batteryPct": 71.1,
        "healthPct": 88.0,
        "task": {"currentTaskId": "7a1c9d40-2b83-4f18-90cd-5e7ba21f6d03", "taskType": "HAUL_LOOP", "progressPct": 78.0, "tonsMoved": 62.5, "throughputTph": 12.0},
    },
    {
        "id": "f60a29c7-3b84-4d1e-9c72-8a5b1d0e4f66",
        "designation": "DOGGE-07",
        "class": "HEAVY_EXCAVATOR",
        "model": "HR-Traverse Digger Mk3",
        "serialNumber": "HTD3-0117",
        "state": "FAULT",
        "siteId": "f18c3d92-74ae-4c07-9e5b-3b60d28af144",
        "baseStationId": "e70b39a5-2c48-4d1f-9b6a-84fc0e2d7b13",
        "zoneId": None,
        "batteryPct": 12.0,
        "healthPct": 41.5,
        "task": {"currentTaskId": None, "taskType": None, "progressPct": 0.0, "tonsMoved": 0.0, "throughputTph": 0.0},
        "anomalies": {"openCount": 1, "lastFaultCode": "TRACK_DRIVE_OVERTEMP", "faultHistory": [{"code": "TRACK_DRIVE_OVERTEMP", "at": "2035-06-10T18:02:00Z", "severity": "MAJOR"}]},
    },
]

RELAY_NETS = [
    {
        "id": "net-belt-1",
        "name": "BELT-RELAY-NET-1",
        "band": "Ka",
        "helloIntervalS": 10,
        "deadIntervalS": 40,
        "networkType": "BROADCAST_RELAY",
        "area": "0.0.52-HELIOS",
        "lsdbMaxAgeS": 1800,
    },
    {
        "id": "net-ceres-1",
        "name": "CERES-GROUND-NET",
        "band": "X",
        "helloIntervalS": 30,
        "deadIntervalS": 120,
        "networkType": "POINT_TO_MULTIPOINT",
        "area": "0.0.52-HELIOS",
        "lsdbMaxAgeS": 3600,
    },
]

# (net, satellite, router priority) - priority 0 means "never a candidate", plain DROther
ADJACENCIES = [
    ("net-belt-1", HEPHAESTUS_7["id"], 200),
    ("net-belt-1", RELAY_NODE_4["id"], 100),
    ("net-belt-1", COLD_STANDBY_VESTA["id"], 50),
    ("net-belt-1", DSN_CERES["id"], 0),
    ("net-ceres-1", HEPHAESTUS_7["id"], 10),
    ("net-ceres-1", DSN_CERES["id"], 0),
]

LINKS = [
    ("a94f2c70-6b18-4d5a-92e3-0c7f4a6d8b21", "9f1c4c2e-8b7a-4d6f-9a3e-2c5d7e8f1a44", "PRIMARY", "Ka", "ESTABLISHED", "2035-06-11T13:48:41Z", 0, 62.0),
    ("a94f2c70-6b18-4d5a-92e3-0c7f4a6d8b21", "7e3b1d55-9a48-42c6-b07f-5d1e83c2a694", "SECONDARY", "X", "ESTABLISHED", "2035-06-10T22:05:12Z", 1, 28.0),
    ("a94f2c70-6b18-4d5a-92e3-0c7f4a6d8b21", "c2a58e6f-1d47-4b93-8c0a-6f9d2b41e773", "COLD_STANDBY", "X", "STANDBY", None, None, 10.0),
    ("f18c3d92-74ae-4c07-9e5b-3b60d28af144", "7e3b1d55-9a48-42c6-b07f-5d1e83c2a694", "PRIMARY", "X", "ESTABLISHED", "2035-06-11T13:40:00Z", 0, 100.0),
    ("0d6b7a48-2f91-4c3d-84ae-91e5f7b0c2d6", "9f1c4c2e-8b7a-4d6f-9a3e-2c5d7e8f1a44", "SURVEY", "Ka", "ESTABLISHED", "2035-06-11T13:55:00Z", 0, 100.0),
]

BACKUPS = [
    ("7e3b1d55-9a48-42c6-b07f-5d1e83c2a694", "9f1c4c2e-8b7a-4d6f-9a3e-2c5d7e8f1a44", "HOT_STANDBY_ROUND_ROBIN", 0.65),
    ("4b7d9f01-3c2a-4e8b-9f16-7a2c8d5b6e10", "9f1c4c2e-8b7a-4d6f-9a3e-2c5d7e8f1a44", "HOT_STANDBY_ROUND_ROBIN", 0.65),
    ("c2a58e6f-1d47-4b93-8c0a-6f9d2b41e773", "9f1c4c2e-8b7a-4d6f-9a3e-2c5d7e8f1a44", "COLD_STANDBY", 0.40),
]

REPORTS = [
    {
        "id": "d58f1c02-9b47-4e6a-8c3d-71a0f9b26e58",
        "schema": "base.telemetry.report.v1",
        "generatedAt": "2035-06-11T14:03:41Z",
        "senderId": "5c1e9a83-2f64-4b7a-8d21-9e0c7b4f6a52",
        "siteId": "a94f2c70-6b18-4d5a-92e3-0c7f4a6d8b21",
        "recipientSatelliteId": "9f1c4c2e-8b7a-4d6f-9a3e-2c5d7e8f1a44",
        "priority": "PRODUCTION",
        "seq": 104882,
        "payload": {
            "healthScore": 0.88,
            "production": {"refinedTonsLastHour": 41.2, "oreIntakeTonsLastHour": 96.5, "fleetActiveCount": 3},
            "criticalAlerts": [{"code": "ANCHOR_03_HOLD_LOW", "severity": "MAJOR", "suggestedAction": "RE_ANCHOR_OR_RELOCATE"}],
            "robotDelta": [
                {"robotId": "8a2f6d31-5b04-4c97-9a8e-1d6c4f7b20e5", "state": "ACTIVE", "batteryPct": 62.4},
                {"robotId": "b41e07c9-8a2d-46f1-93c5-7e0b28af5d13", "state": "RETURNING", "batteryPct": 71.1},
            ],
        },
    }
]


def _robot_doc(spec: dict) -> dict:
    doc = json.loads(json.dumps(ROBOT_TEMPLATE))
    doc.update(
        {
            "id": spec["id"],
            "designation": spec["designation"],
            "class": spec["class"],
            "model": spec["model"],
            "serialNumber": spec["serialNumber"],
            "state": spec["state"],
            "ownership": {
                "baseStationId": spec["baseStationId"],
                "tenure": "OWNED",
                "siteId": spec["siteId"],
                "zoneId": spec["zoneId"],
                "hostBodyId": "b6e0c1d4-77a3-4c8e-91f2-0d5a6b3c8e19",
            },
        }
    )
    doc["tags"] = spec.get("tags", [])
    metrics = doc["metrics"]
    metrics["healthScore"] = round(spec["healthPct"] / 100, 2)
    metrics["power"]["batteryPct"] = spec["batteryPct"]
    metrics["tasking"].update(spec["task"])
    if "anomalies" in spec:
        metrics["anomalies"] = spec["anomalies"]
    return doc


def seed(conn) -> None:
    t0 = "2035-06-11T14:03:41Z"
    for sat in [HEPHAESTUS_7, RELAY_NODE_4, DSN_CERES, COLD_STANDBY_VESTA]:
        metrics = sat.pop("metrics", {})
        conn.execute(
            "INSERT INTO satellites (id, name, operator, model, serial_number, status, doc, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (sat["id"], sat["name"], sat["operator"], sat["model"], sat["serialNumber"], sat["status"], json.dumps(sat), t0, t0),
        )
        conn.execute(
            "INSERT INTO metrics (entity_type, entity_id, collected_at, payload) VALUES (?,?,?,?)",
            ("satellite", sat["id"], metrics.get("collectedAt", t0), json.dumps(metrics)),
        )
        sat["metrics"] = metrics

    for base in [PSYCHE_DRILL_02, PSYCHE_DRILL_01, SURVEY_GRID_NE]:
        site_id = base["siteRef"]["siteId"]
        metrics = base.pop("metrics", {})
        conn.execute(
            "INSERT INTO sites (id, name, designation, host_body, base_station_id, status, doc, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (
                site_id,
                base["name"],
                base["siteRef"]["designation"],
                base["siteRef"]["hostBody"]["provisionalName"],
                base["id"],
                base["status"],
                json.dumps(base),
                t0,
                t0,
            ),
        )
        conn.execute(
            "INSERT INTO metrics (entity_type, entity_id, collected_at, payload) VALUES (?,?,?,?)",
            ("site", site_id, metrics.get("collectedAt", t0), json.dumps(metrics)),
        )
        base["metrics"] = metrics

    for spec in ROBOTS:
        doc = _robot_doc(spec)
        conn.execute(
            "INSERT INTO robots (id, designation, robot_class, status, state, site_id, base_station_id, zone_id,"
            " battery_pct, health_pct, doc, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                spec["id"],
                spec["designation"],
                spec["class"],
                spec.get("status", "OPERATIONAL"),
                spec["state"],
                spec["siteId"],
                spec["baseStationId"],
                spec["zoneId"],
                spec["batteryPct"],
                spec["healthPct"],
                json.dumps(doc),
                t0,
                t0,
            ),
        )
        conn.execute(
            "INSERT INTO metrics (entity_type, entity_id, collected_at, payload) VALUES (?,?,?,?)",
            ("robot", spec["id"], t0, json.dumps(doc["metrics"])),
        )

    for row in LINKS:
        conn.execute(
            "INSERT INTO links (site_id, satellite_id, role, band, status, established_at, last_report_at, missed_reports,"
            " share_pct) VALUES (?,?,?,?,?,?,?,?,?)",
            (*row[:5], t0 if row[4] == "ESTABLISHED" else None, *row[5:]),
        )
    conn.executemany(
        "INSERT INTO satellite_backups (satellite_id, primary_satellite_id, policy, failover_threshold_health, created_at)"
        " VALUES (?,?,?,?,?)",
        [(b, p, pol, th, t0) for b, p, pol, th in BACKUPS],
    )

    for net in RELAY_NETS:
        conn.execute(
            "INSERT INTO relay_nets (id, name, band, hello_interval_s, dead_interval_s, doc, created_at) VALUES (?,?,?,?,?,?,?)",
            (net["id"], net["name"], net["band"], net["helloIntervalS"], net["deadIntervalS"], json.dumps(net), t0),
        )
    for net_id, satellite_id, priority in ADJACENCIES:
        # shortcut: the seeded OSPF timers run on the real clock, unlike the sample documents' dates,
        # so the neighbor table is alive at start; refresh it with POST /relay-nets/{net}/peers/{sat}/hello.
        conn.execute(
            "INSERT INTO adjacencies (net_id, satellite_id, priority, state, last_hello_at, formed_at) VALUES (?,?,?,?,?,?)",
            (net_id, satellite_id, priority, "FULL", clock.iso(), clock.iso_in(-6 * 3600)),
        )
        net = next(n for n in RELAY_NETS if n["id"] == net_id)
        satellite = next(s for s in [HEPHAESTUS_7, RELAY_NODE_4, DSN_CERES, COLD_STANDBY_VESTA] if s["id"] == satellite_id)
        db.log(
            conn, "INFO", "ospf", f"net {net['name']}",
            f"peer {satellite['name']}({satellite_id[:8]}) adjacency pre-established state=FULL priority={priority}",
            ts=t0,
        )
    for report in REPORTS:
        conn.execute(
            "INSERT INTO reports (id, schema_name, sender_id, site_id, recipient_satellite_id, priority, seq,"
            " generated_at, payload, accepted_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                report["id"],
                report["schema"],
                report["senderId"],
                report["siteId"],
                report["recipientSatelliteId"],
                report["priority"],
                report["seq"],
                report["generatedAt"],
                json.dumps(report["payload"]),
                report["generatedAt"],
            ),
        )

    for user in USERS:
        conn.execute(
            "INSERT INTO users (username, password_hash, role, display_name, created_at) VALUES (?,?,?,?,?)",
            (user["username"], auth.hash_password(user["password"]), user["role"], user["displayName"], t0),
        )
