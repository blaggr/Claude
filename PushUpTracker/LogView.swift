import SwiftUI

struct LogView: View {
    @EnvironmentObject private var log: PushUpLog

    var body: some View {
        List {
            if log.entries.isEmpty {
                Text("No sessions yet.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            } else {
                ForEach(log.entries) { entry in
                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(entry.date, style: .time)
                                .font(.body)
                            Text(entry.date, style: .date)
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                        Spacer()
                        Text("\(entry.count)")
                            .font(.title3)
                            .monospacedDigit()
                            .bold()
                    }
                }
                .onDelete(perform: log.delete)
            }
        }
        .navigationTitle("History")
    }
}

#Preview {
    NavigationStack {
        LogView().environmentObject(PushUpLog())
    }
}
