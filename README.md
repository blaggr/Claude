# Push-Up Tracker (watchOS)

A standalone Apple Watch app that:

- Nudges you with a notification every waking hour to do push-ups.
- When you tap "Start", uses the wrist motion sensors to count your reps automatically.
- Tap "Done" and the session is logged to local history.

## What's in this repo

```
PushUpTracker/
├── PushUpTrackerApp.swift       App entry point + permissions bootstrap
├── ContentView.swift            Root view (today's count, history link, Start)
├── SessionView.swift            Live rep-counting view during a workout
├── LogView.swift                History list
├── PushUpDetector.swift         CoreMotion-based rep detector
├── WorkoutManager.swift         HKWorkoutSession lifecycle (keeps motion alive)
├── NotificationScheduler.swift  Hourly local notifications + rescheduling
├── PushUpLog.swift              Data model + JSON persistence
├── Info.plist                   Privacy strings
└── Assets.xcassets/             Empty icon + accent slots
```

## Building it in Xcode

You need Xcode 15+ and an Apple Watch running watchOS 10 or later.

1. **Create a fresh project**: `File → New → Project → watchOS → App`. Name it `PushUpTracker`, language Swift, interface SwiftUI, no tests required.
2. **Replace the template files**: in the project Xcode generated, delete `PushUpTrackerApp.swift`, `ContentView.swift`, and (if present) `Item.swift`.
3. **Drag in the sources**: drag every file under `PushUpTracker/` from this repo into the Xcode project navigator, choosing "Copy items if needed" and adding to the watch app target.
4. **Replace `Info.plist`** with the one from this repo (or merge these keys into the auto-generated Info: `NSMotionUsageDescription`, `NSHealthShareUsageDescription`, `NSHealthUpdateUsageDescription`).
5. **Capabilities** (target → Signing & Capabilities):
   - Add `HealthKit`.
   - Add `Background Modes` → check `Workout processing`.
6. Build and run on your watch (the Simulator can't produce real motion data, so detection will not fire there — the rest of the UI works).

## How rep detection works

Wearing the watch on either wrist, in a normal push-up position, the watch moves up and down with your torso. The detector:

1. Starts an `HKWorkoutSession` (functional strength, indoor). This keeps CoreMotion sampling even when the screen sleeps because your wrist is on the floor.
2. Subscribes to `CMMotionManager.deviceMotion` at 50 Hz.
3. For each sample, projects `userAcceleration` (gravity-removed) onto the world-vertical axis using the device's gravity vector:
   `a_vert = -(a·g) / |g|`
4. Smooths with a single-pole IIR filter (α = 0.3).
5. Runs a small state machine: a rep is counted when a downward acceleration peak (≤ −0.25 g — the top of the rep, decelerating into the descent) is followed by an upward acceleration peak (≥ +0.25 g — the bottom, arms driving the body back up) within 0.3–2.0 s. A 0.6 s refractory period prevents double-counts.
6. Triggers a light haptic per rep.

Thresholds live at the top of `PushUpDetector.swift` if your reps are slower/lighter than the defaults.

## Reminders

`NotificationScheduler` registers one `UNCalendarNotificationTrigger` per hour from 07:00 to 22:00 local time (repeating daily) — so you get a nudge at the top of every waking hour. Adjust the waking-hours range at the top of `NotificationScheduler.swift`.

## Limitations / known gotchas

- The detector only runs while the app is foreground inside a workout session. The flow assumes you tap the notification → tap Start → do push-ups → tap Done.
- Watch on the wrist is required (obviously). Motion patterns differ wildly between push-up variants; clap/diamond/decline push-ups may need re-tuning.
- The Simulator does not generate motion. Test on hardware.
- No HealthKit workouts are saved to the Health app yet (the workout session is used only to keep sensors live). Wiring this up via `HKLiveWorkoutBuilder.endCollection` + `finishWorkout` is a small follow-up if you want it.
