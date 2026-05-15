import SwiftUI

struct ContentView: View {
    @EnvironmentObject private var log: PushUpLog
    @State private var showSession = false

    var body: some View {
        NavigationStack {
            VStack(spacing: 12) {
                VStack(spacing: 2) {
                    Text("\(log.todayCount)")
                        .font(.system(size: 56, weight: .bold, design: .rounded))
                        .monospacedDigit()
                    Text("today")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }

                Button {
                    showSession = true
                } label: {
                    Label("Start", systemImage: "figure.strengthtraining.functional")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)

                NavigationLink {
                    LogView()
                } label: {
                    Label("History", systemImage: "list.bullet")
                }
                .buttonStyle(.bordered)
            }
            .padding(.vertical, 4)
            .navigationTitle("Push-Ups")
        }
        .sheet(isPresented: $showSession) {
            SessionView()
                .environmentObject(log)
        }
    }
}

#Preview {
    ContentView().environmentObject(PushUpLog())
}
