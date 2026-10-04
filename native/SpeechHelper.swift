import Foundation
import AVFoundation
import Speech

func emit(_ value: [String: Any]) {
    if let data = try? JSONSerialization.data(withJSONObject: value), let text = String(data: data, encoding: .utf8) {
        print(text)
        fflush(stdout)
    }
}
if CommandLine.arguments.contains("--clap-check") {
    checkClapDetector()
    emit(["ok": true, "detector": "double-clap"])
    exit(0)
}
if CommandLine.arguments.contains("--check") {
    emit(["ok": true, "engine": "Apple Speech", "locale": "ko-KR"])
    exit(0)
}
final class Listener {
    let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "ko-KR"))
    var engine: AVAudioEngine?
    var task: SFSpeechRecognitionTask?
    var request: SFSpeechAudioBufferRecognitionRequest?
    var timer: Timer?
    var transcript = ""
    var changed = Date()
    var began = Date()
    var generation = 0
    var restarting = false
    var errors = 0

    func start() {
        guard let recognizer = recognizer, recognizer.isAvailable else {
            emit(["type": "error", "text": "Apple 음성 인식을 사용할 수 없어요. 인터넷 연결과 언어 설정을 확인하세요."])
            exit(1)
        }
        generation += 1
        let current = generation
        restarting = false
        transcript = ""
        began = Date()
        changed = Date()
        let engine = AVAudioEngine()
        let request = SFSpeechAudioBufferRecognitionRequest()
        request.shouldReportPartialResults = true
        // Prefer on-device recognition when the installed Korean model supports it.
        if recognizer.supportsOnDeviceRecognition { request.requiresOnDeviceRecognition = true }
        let node = engine.inputNode
        let format = node.outputFormat(forBus: 0)
        guard format.sampleRate > 0 && format.channelCount > 0 else {
            emit(["type": "error", "text": "사용 가능한 마이크가 없어요."])
            exit(1)
        }
        node.installTap(onBus: 0, bufferSize: 1024, format: format) { buffer, _ in request.append(buffer) }
        self.engine = engine
        self.request = request
        task = recognizer.recognitionTask(with: request) { result, error in
            DispatchQueue.main.async {
                guard self.generation == current && !self.restarting else { return }
                if let result = result {
                    let text = result.bestTranscription.formattedString
                    if text != self.transcript {
                        self.transcript = text
                        self.changed = Date()
                        self.errors = 0
                        emit(["type": "partial", "text": text])
                    }
                    if result.isFinal { self.restart(deliver: true) }
                } else if error != nil {
                    self.errors += 1
                    if self.errors > 4 {
                        emit(["type": "error", "text": "음성 인식이 반복해서 끊겼어요. 마이크 권한과 인터넷 연결을 확인하세요."])
                        exit(1)
                    }
                    self.restart(deliver: false)
                }
            }
        }
        do {
            engine.prepare()
            try engine.start()
            emit(["type": "ready", "text": "마이크 연결됨"])
        } catch {
            emit(["type": "error", "text": "마이크를 시작하지 못했어요."])
            exit(1)
        }
        timer = Timer.scheduledTimer(withTimeInterval: 0.2, repeats: true) { _ in
            if !self.transcript.isEmpty && Date().timeIntervalSince(self.changed) > 1.25 {
                self.restart(deliver: true)
            } else if Date().timeIntervalSince(self.began) > 45 {
                self.restart(deliver: true)
            }
        }
    }
    func restart(deliver: Bool) {
        guard !restarting else { return }
        restarting = true
        if deliver && !transcript.isEmpty { emit(["type": "utterance", "text": transcript]) }
        timer?.invalidate()
        timer = nil
        engine?.stop()
        engine?.inputNode.removeTap(onBus: 0)
        request?.endAudio()
        task?.cancel()
        task = nil
        request = nil
        engine = nil
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) { self.start() }
    }
}
final class ClapListener {
    let engine = AVAudioEngine()
    let detector = ClapDetector()
    func start() {
        let node = engine.inputNode
        let format = node.outputFormat(forBus: 0)
        guard format.sampleRate > 0 && format.channelCount > 0 else {
            emit(["type":"error", "text":"사용 가능한 마이크가 없어요."])
            exit(1)
        }
        node.installTap(onBus: 0, bufferSize: 1024, format: format) { buffer, _ in
            guard let samples = buffer.floatChannelData?[0] else { return }
            let count = Int(buffer.frameLength)
            guard count > 0 else { return }
            var energy: Float = 0
            var peak: Float = 0
            for i in 0..<count {
                let x = abs(samples[i])
                peak = max(peak, x)
                energy += x*x
            }
            if self.detector.process(rms: sqrt(energy/Float(count)), peak: peak, at: ProcessInfo.processInfo.systemUptime) {
                emit(["type":"clap_pair", "text":"박수 두 번 감지"])
            }
        }
        do {
            engine.prepare()
            try engine.start()
            emit(["type":"ready", "text":"박수 대기 중"])
        } catch {
            emit(["type":"error", "text":"박수 감지 마이크를 켜지 못했어요."])
            exit(1)
        }
    }
}
let listener = Listener()
let clapListener = ClapListener()
AVCaptureDevice.requestAccess(for: .audio) { allowed in
    guard allowed else {
        emit(["type": "error", "text": "시스템 설정에서 JarvisCyber 마이크 권한을 허용하세요."])
        exit(1)
    }
    if CommandLine.arguments.contains("--clap") {
        DispatchQueue.main.async { clapListener.start() }
        return
    }
    SFSpeechRecognizer.requestAuthorization { status in
        guard status == .authorized else {
            emit(["type": "error", "text": "시스템 설정에서 JarvisCyber 음성 인식 권한을 허용하세요."])
            exit(1)
        }
        DispatchQueue.main.async { listener.start() }
    }
}
RunLoop.main.run()
