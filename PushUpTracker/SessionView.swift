import SwiftUI
import WatchKit

struct SessionView: View {
    @EnvironmentObject private var log: PushUpLog
    @Environment(\.dismiss) private var dismiss

    @StateObject private var detector = PushUpDetector()
    @StateObject private var workout = WorkoutManager()

    @State private var startError: String?

    var body: some View {
        VStack(spacing: 10) {
            Text("\(detector.count)")
                .font(.system(size: 80, weight: .bold, design: .rounded))
                .monospacedDigit()
                .contentTransition(.numericText())
                .animation(.snappy, value: detector.count)

            Text(detector.isRunning ? "Counting…" : "Get into position")
                .font(.caption2)
                .foregroundStyle(.secondary)

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
        .onChange(of: detector.count) { _, _ in
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
        if save && count > 0 {
            log.record(count: count)
        }
        dismiss()
    }
}

#Preview {
    SessionView().environmentObject(PushUpLog())
}
