import SwiftUI
import WatchKit

struct SessionView: View {
    static let goal: Int = 20

    @EnvironmentObject private var log: PushUpLog
    @Environment(\.dismiss) private var dismiss

    @StateObject private var detector = PushUpDetector()
    @StateObject private var workout = WorkoutManager()

    @State private var startError: String?
    @State private var loggedEntryID: UUID?

    private var goalReached: Bool { detector.count >= Self.goal }

    var body: some View {
        VStack(spacing: 10) {
            Text("\(detector.count)")
                .font(.system(size: 80, weight: .bold, design: .rounded))
                .monospacedDigit()
                .contentTransition(.numericText())
                .foregroundStyle(goalReached ? .green : .primary)
                .animation(.snappy, value: detector.count)

            Text(subtitle)
                .font(.caption2)
                .foregroundStyle(goalReached ? .green : .secondary)

            if let startError {
                Text(startError)
                    .font(.caption2)
                    .foregroundStyle(.red)
                    .multilineTextAlignment(.center)
            }

            HStack {
                Button(role: .cancel) {
                    Task { await stop(save: false) }
                } label: {
                    Image(systemName: "xmark")
                        .frame(maxWidth: .infinity)
                }

                Button {
                    Task { await stop(save: true) }
                } label: {
                    Image(systemName: "checkmark")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .tint(.green)
            }
        }
        .padding(.horizontal, 8)
        .onAppear { Task { await start() } }
        .onChange(of: detector.count) { _, newValue in
            guard newValue > 0 else { return }
            handleRep(count: newValue)
        }
    }

    private var subtitle: String {
        if !detector.isRunning && startError == nil {
            return "Get into position"
        } else if goalReached {
            return "Goal reached — logged"
        } else {
            return "\(detector.count) / \(Self.goal)"
        }
    }

    private func handleRep(count: Int) {
        if count >= Self.goal {
            if let id = loggedEntryID {
                WKInterfaceDevice.current().play(.click)
                log.update(id: id, count: count)
            } else {
                WKInterfaceDevice.current().play(.success)
                loggedEntryID = log.record(count: count).id
            }
        } else {
            WKInterfaceDevice.current().play(.click)
        }
    }

    private func start() async {
        do {
            try await workout.start()
            detector.start()
        } catch {
            startError = "Couldn't start workout: \(error.localizedDescription)"
        }
    }

    private func stop(save: Bool) async {
        let count = detector.count
        detector.stop()
        await workout.stop()

        if save {
            if loggedEntryID == nil && count > 0 {
                log.record(count: count)
            }
        } else if let id = loggedEntryID {
            log.delete(id: id)
            loggedEntryID = nil
        }

        dismiss()
    }
}

#Preview {
    SessionView().environmentObject(PushUpLog())
}
