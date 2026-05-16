import Foundation

struct PushUpEntry: Codable, Identifiable, Equatable {
    let id: UUID
    let date: Date
    let count: Int

    init(id: UUID = UUID(), date: Date = Date(), count: Int) {
        self.id = id
        self.date = date
        self.count = count
    }
}

@MainActor
final class PushUpLog: ObservableObject {
    @Published private(set) var entries: [PushUpEntry] = []

    private let fileURL: URL

    init() {
        let dir = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first!
        self.fileURL = dir.appendingPathComponent("pushup-log.json")
        load()
    }

    var todayCount: Int {
        let calendar = Calendar.current
        return entries
            .filter { calendar.isDateInToday($0.date) }
            .reduce(0) { $0 + $1.count }
    }

    @discardableResult
    func record(count: Int) -> PushUpEntry {
        let entry = PushUpEntry(count: count)
        entries.insert(entry, at: 0)
        save()
        return entry
    }

    func update(id: UUID, count: Int) {
        guard let index = entries.firstIndex(where: { $0.id == id }) else { return }
        let existing = entries[index]
        entries[index] = PushUpEntry(id: existing.id, date: existing.date, count: count)
        save()
    }

    func delete(id: UUID) {
        entries.removeAll { $0.id == id }
        save()
    }

    func delete(at offsets: IndexSet) {
        entries.remove(atOffsets: offsets)
        save()
    }

    private func load() {
        guard let data = try? Data(contentsOf: fileURL),
              let decoded = try? JSONDecoder().decode([PushUpEntry].self, from: data) else { return }
        entries = decoded.sorted { $0.date > $1.date }
    }

    private func save() {
        guard let data = try? JSONEncoder().encode(entries) else { return }
        try? data.write(to: fileURL, options: .atomic)
    }
}
