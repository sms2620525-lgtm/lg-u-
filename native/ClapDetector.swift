import Foundation

// Detect two brief attacks, separated by a quiet gap. No speech/audio is retained.
final class ClapDetector {
    var floor: Float = 0.003
    var onset: Double?
    var first: Double?
    var lastEnd: Double = -100
    var cooldown: Double = -100
    func process(rms: Float, peak: Float, at t: Double) -> Bool {
        if t < cooldown { return false }
        let loud = peak > max(0.18, floor * 7) && rms > max(0.025, floor * 3)
        if loud {
            if onset == nil { onset = t }
            return false
        }
        floor = max(0.001, min(0.06, floor * 0.98 + rms * 0.02))
        guard let start = onset else {
            if let a = first, t-a > 1.0 { first = nil }
            return false
        }
        onset = nil
        let duration = t-start
        let quietGap = start-lastEnd
        lastEnd = t
        guard duration <= 0.12 && quietGap >= 0.10 else { first = nil; return false }
        if let a = first, start-a >= 0.18 && start-a <= 0.9 {
            first = nil
            cooldown = t+2.0
            return true
        }
        first = start
        return false
    }
}

func checkClapDetector() {
    func pulse(_ d: ClapDetector, _ t: Double, _ length: Double = 0.04) -> Bool {
        _ = d.process(rms: 0.15, peak: 0.8, at: t)
        return d.process(rms: 0.002, peak: 0.006, at: t+length)
    }
    let pair = ClapDetector()
    precondition(!pulse(pair, 1))
    precondition(pulse(pair, 1.4))
    precondition(!pulse(pair, 1.8))
    let separated = ClapDetector()
    precondition(!pulse(separated, 1))
    precondition(!pulse(separated, 3))
    let sustained = ClapDetector()
    precondition(!pulse(sustained, 1, 0.5))
    precondition(!pulse(sustained, 1.8))
    let noisy = ClapDetector()
    for i in 0..<100 {
        precondition(!noisy.process(rms: 0.01, peak: 0.06, at: Double(i)*0.02))
    }
}
