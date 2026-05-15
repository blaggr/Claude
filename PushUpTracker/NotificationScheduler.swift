import Foundation
import UserNotifications

final class NotificationScheduler {
    static let shared = NotificationScheduler()
    private init() {}

    private let firstHour = 7   // 07:00 inclusive
    private let lastHour = 22   // 22:00 inclusive
    private let categoryID = "pushup.reminder"

    func requestAuthorization() async {
        let center = UNUserNotificationCenter.current()
        _ = try? await center.requestAuthorization(options: [.alert, .sound])
    }

    func scheduleHourlyReminders() {
        let center = UNUserNotificationCenter.current()
        center.removePendingNotificationRequests(withIdentifiers: identifiers())

        for hour in firstHour...lastHour {
            var components = DateComponents()
            components.hour = hour
            components.minute = 0

            let content = UNMutableNotificationContent()
            content.title = "Push-up break"
            content.body = "Knock out a set. Tap to start counting."
            content.sound = .default
            content.categoryIdentifier = categoryID

            let trigger = UNCalendarNotificationTrigger(dateMatching: components, repeats: true)
            let request = UNNotificationRequest(identifier: id(for: hour),
                                                content: content,
                                                trigger: trigger)
            center.add(request)
        }
    }

    private func id(for hour: Int) -> String { "pushup.hour.\(hour)" }

    private func identifiers() -> [String] {
        (firstHour...lastHour).map { id(for: $0) }
    }
}
