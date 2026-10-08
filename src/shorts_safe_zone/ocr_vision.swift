// ocr_vision.swift - text recognition with the macOS Vision framework (no extra install).
// Usage: ocr_vision a.png b.png ...   -> one JSON line on stdout:
//   {"files":[{"file":..., "w":..., "h":..., "items":[{"text":..., "conf":0.0-1.0, "box":[x,y,w,h]}], "error":null}]}
// box is in image pixels, origin at the top-left corner.
// Recognition: VNRecognizeTextRequest, accurate level, no language correction.
// Languages default to en-US; override with the OCR_VISION_LANGS environment variable
// (comma separated, e.g. "ko-KR,en-US").
import Foundation
import Vision
import AppKit

func ocr(_ path: String, _ langs: [String]) -> [String: Any] {
    var out: [String: Any] = ["file": path, "items": [], "error": NSNull()]
    guard let img = NSImage(contentsOfFile: path),
          let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
        out["error"] = "cannot open image"
        return out
    }
    let W = Double(cg.width), H = Double(cg.height)
    out["w"] = cg.width; out["h"] = cg.height
    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate
    req.recognitionLanguages = langs
    req.usesLanguageCorrection = false
    req.minimumTextHeight = 0.0
    let handler = VNImageRequestHandler(cgImage: cg, options: [:])
    do { try handler.perform([req]) } catch {
        out["error"] = "\(error)"
        return out
    }
    var items: [[String: Any]] = []
    for obs in req.results ?? [] {
        guard let cand = obs.topCandidates(1).first else { continue }
        let b = obs.boundingBox   // normalized, origin at the bottom-left corner
        let x = b.origin.x * W, w = b.size.width * W
        let h = b.size.height * H, y = (1.0 - b.origin.y - b.size.height) * H
        items.append(["text": cand.string, "conf": Double(cand.confidence),
                      "box": [Int(x.rounded()), Int(y.rounded()), Int(w.rounded()), Int(h.rounded())]])
    }
    out["items"] = items
    return out
}

let args = Array(CommandLine.arguments.dropFirst())
if args.isEmpty {
    FileHandle.standardError.write("usage: ocr_vision a.png [b.png ...]\n".data(using: .utf8)!)
    exit(2)
}
var langs = ["en-US"]
if let e = ProcessInfo.processInfo.environment["OCR_VISION_LANGS"], !e.isEmpty {
    langs = e.split(separator: ",").map { String($0).trimmingCharacters(in: .whitespaces) }
}
var files: [[String: Any]] = []
for p in args { files.append(ocr(p, langs)) }
let data = try! JSONSerialization.data(withJSONObject: ["files": files], options: [])
FileHandle.standardOutput.write(data)
FileHandle.standardOutput.write("\n".data(using: .utf8)!)
