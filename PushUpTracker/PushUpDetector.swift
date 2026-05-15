import Combine
import CoreMotion
import Foundation

@MainActor
final class PushUpDetector: ObservableObject {
    // Tunables. Units: g for accel, seconds for time.
    private let downThreshold: Double = -0.25
    private let upThreshold: Double = 0.25
    private let minPairInterval: Double = 0.30
    private let maxPairInterval: Double = 2.00
    private let refractory: Double = 0.60
    private let filterAlpha: Double = 0.30
    private let sampleHz: Double = 50

    @Published private(set) var count: Int = 0
    @Published private(set) var isRunning: Bool = false

    private let motion = CMMotionManager()
    private let queue = OperationQueue()

    private var filtered: Double = 0
    private var lastDownTime: TimeInterval?
    private var lastRepTime: TimeInterval = 0

    init() {
        queue.name = "PushUpDetector.motion"
        queue.qualityOfService = .userInteractive
    }

    func start() {
        guard motion.isDeviceMotionAvailable, !isRunning else { return }
        motion.deviceMotionUpdateInterval = 1.0 / sampleHz
        count = 0
        filtered = 0
        lastDownTime = nil
        lastRepTime = 0
        isRunning = true

        motion.startDeviceMotionUpdates(to: queue) { [weak self] data, _ in
            guard let self, let data else { return }
            let sample = data
            Task { @MainActor [weak self] in
                self?.process(sample)
            }
        }
    }

    func stop() {
        guard isRunning else { return }
        motion.stopDeviceMotionUpdates()
        isRunning = false
    }

    private func process(_ data: CMDeviceMotion) {
        let g = data.gravity
        let a = data.userAcceleration
        let gMag = max(sqrt(g.x*g.x + g.y*g.y + g.z*g.z), 1e-6)
        // Component of user acceleration along world-up (gravity points "down" in device frame).
        let verticalUp = -(a.x*g.x + a.y*g.y + a.z*g.z) / gMag

        filtered = filterAlpha * verticalUp + (1 - filterAlpha) * filtered

        let t = data.timestamp

        if filtered <= downThreshold {
            // Top of the rep — body about to descend.
            if lastDownTime == nil {
                lastDownTime = t
            }
        } else if filtered >= upThreshold, let down = lastDownTime {
            let gap = t - down
            if gap >= minPairInterval, gap <= maxPairInterval, (t - lastRepTime) >= refractory {
                count += 1
                lastRepTime = t
                lastDownTime = nil
            } else if gap > maxPairInterval {
                lastDownTime = t  // stale; restart pairing from this peak instead
            }
        }
    }
}
