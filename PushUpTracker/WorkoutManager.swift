import Foundation
import HealthKit

@MainActor
final class WorkoutManager: ObservableObject {
    private let store = HKHealthStore()
    private var session: HKWorkoutSession?
    private var builder: HKLiveWorkoutBuilder?

    func start() async throws {
        guard HKHealthStore.isHealthDataAvailable() else {
            throw NSError(domain: "WorkoutManager", code: 1,
                          userInfo: [NSLocalizedDescriptionKey: "Health data unavailable"])
        }

        let typesToShare: Set = [HKQuantityType.workoutType()]
        let typesToRead: Set<HKObjectType> = [
            HKQuantityType.quantityType(forIdentifier: .heartRate)!,
            HKQuantityType.quantityType(forIdentifier: .activeEnergyBurned)!,
        ]
        try await store.requestAuthorization(toShare: typesToShare, read: typesToRead)

        let config = HKWorkoutConfiguration()
        config.activityType = .functionalStrengthTraining
        config.locationType = .indoor

        let session = try HKWorkoutSession(healthStore: store, configuration: config)
        let builder = session.associatedWorkoutBuilder()
        builder.dataSource = HKLiveWorkoutDataSource(healthStore: store,
                                                    workoutConfiguration: config)

        self.session = session
        self.builder = builder

        let now = Date()
        session.startActivity(with: now)
        try await builder.beginCollection(at: now)
    }

    func stop() async {
        guard let session, let builder else { return }
        let end = Date()
        session.end()
        try? await builder.endCollection(at: end)
        // We don't finalize the workout into HealthKit on purpose — the session
        // exists only to keep CoreMotion alive. Drop the builder; HK will discard.
        self.session = nil
        self.builder = nil
    }
}
