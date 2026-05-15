import SwiftUI

@main
struct PushUpTrackerApp: App {
    @StateObject private var log = PushUpLog()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(log)
                .task {
                    await NotificationScheduler.shared.requestAuthorization()
                    NotificationScheduler.shared.scheduleHourlyReminders()
                }
        }
    }
}
