#!/usr/bin/env swift
//
// extract-subject.swift — extract the foreground subject from an image and
// write it as a PNG with a transparent background.
//
// Backed by Apple Vision's VNGenerateForegroundInstanceMaskRequest (macOS
// 14+). Same underlying mask used by Preview / Photos for "subject lift".
//
// Usage:
//   ./scripts/extract-subject.swift <input> <output>
//
// Exit codes:
//   0  success — wrote output.png
//   1  Vision returned no foreground instance (rare, but happens when the
//      input is mostly background or low-confidence)
//   2  I/O / argument failure
//

import Foundation
import Vision
import CoreImage
import CoreImage.CIFilterBuiltins
import AppKit

let args = CommandLine.arguments
guard args.count == 3 else {
    FileHandle.standardError.write(Data("usage: \(args[0]) <input> <output>\n".utf8))
    exit(2)
}
let inputPath = args[1]
let outputPath = args[2]

guard let nsImage = NSImage(contentsOfFile: inputPath),
      let cgImage = nsImage.cgImage(forProposedRect: nil, context: nil, hints: nil)
else {
    FileHandle.standardError.write(Data("error: could not read input image \(inputPath)\n".utf8))
    exit(2)
}

let ciImage = CIImage(cgImage: cgImage)
let request = VNGenerateForegroundInstanceMaskRequest()
let handler = VNImageRequestHandler(ciImage: ciImage)

do {
    try handler.perform([request])
} catch {
    FileHandle.standardError.write(Data("error: Vision request failed: \(error)\n".utf8))
    exit(2)
}

guard let result = request.results?.first else {
    FileHandle.standardError.write(Data("warn: no foreground instance found in \(inputPath)\n".utf8))
    exit(1)
}

let maskPixelBuffer: CVPixelBuffer
do {
    maskPixelBuffer = try result.generateScaledMaskForImage(
        forInstances: result.allInstances,
        from: handler
    )
} catch {
    FileHandle.standardError.write(Data("error: mask generation failed: \(error)\n".utf8))
    exit(2)
}

let maskImage = CIImage(cvPixelBuffer: maskPixelBuffer)

let blend = CIFilter.blendWithMask()
blend.inputImage = ciImage
blend.maskImage = maskImage
blend.backgroundImage = CIImage.empty()

guard let outputCI = blend.outputImage else {
    FileHandle.standardError.write(Data("error: blend filter produced no output\n".utf8))
    exit(2)
}

let context = CIContext(options: nil)
guard let outputCG = context.createCGImage(outputCI, from: outputCI.extent) else {
    FileHandle.standardError.write(Data("error: could not render CGImage\n".utf8))
    exit(2)
}

let outputNS = NSImage(cgImage: outputCG, size: NSSize(width: outputCG.width, height: outputCG.height))
guard let tiff = outputNS.tiffRepresentation,
      let rep = NSBitmapImageRep(data: tiff),
      let pngData = rep.representation(using: .png, properties: [:])
else {
    FileHandle.standardError.write(Data("error: could not encode PNG\n".utf8))
    exit(2)
}

let outputURL = URL(fileURLWithPath: outputPath)
do {
    try FileManager.default.createDirectory(
        at: outputURL.deletingLastPathComponent(),
        withIntermediateDirectories: true
    )
    try pngData.write(to: outputURL)
} catch {
    FileHandle.standardError.write(Data("error: could not write output \(outputPath): \(error)\n".utf8))
    exit(2)
}
