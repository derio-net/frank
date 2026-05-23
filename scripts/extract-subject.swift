#!/usr/bin/env swift
//
// extract-subject.swift — extract the foreground subject from an image and
// write it as a PNG with a transparent background.
//
// WHEN TO USE THIS vs. just cropping an existing subject:
//   If a clean character render already exists in
//   .reference-pool/<series>/subjects/ (transparent background, single
//   figure), PREFER cropping that to its alpha bbox — Vision's auto-
//   segmentation under-performs on complex scenes (Frank lying among
//   tools, Frank with elaborate background) and on non-photorealistic
//   characters (Apple's person detector doesn't recognise Frank as a
//   person). Use this script for the case where you have a tile or
//   cover image and no clean subject exists yet.
//
// Two strategies (pick per image; defaults to `foreground`):
//
//   foreground   — VNGenerateForegroundInstanceMaskRequest (macOS 14+).
//                  Same mask Preview / Photos uses for "subject lift".
//                  Best for most images. Output is cropped to the subject's
//                  bounding box.
//
//   person       — VNGeneratePersonSegmentationRequest at .accurate quality
//                  (macOS 12+). Person-targeted; on Frank it typically
//                  returns an empty mask because the character isn't
//                  recognised as a person. Kept for completeness — try on
//                  photorealistic human inputs.
//
// Usage:
//   ./scripts/extract-subject.swift <input> <output> [foreground|person]
//
// Exit codes:
//   0  success — wrote output.png
//   1  Vision returned no usable subject
//   2  I/O / argument failure
//

import Foundation
import Vision
import CoreImage
import CoreImage.CIFilterBuiltins
import AppKit

let args = CommandLine.arguments
guard args.count == 3 || args.count == 4 else {
    FileHandle.standardError.write(Data("usage: \(args[0]) <input> <output> [foreground|person]\n".utf8))
    exit(2)
}
let inputPath = args[1]
let outputPath = args[2]
let strategy = args.count == 4 ? args[3] : "foreground"
guard strategy == "foreground" || strategy == "person" else {
    FileHandle.standardError.write(Data("error: strategy must be 'foreground' or 'person', got '\(strategy)'\n".utf8))
    exit(2)
}

guard let nsImage = NSImage(contentsOfFile: inputPath),
      let cgImage = nsImage.cgImage(forProposedRect: nil, context: nil, hints: nil)
else {
    FileHandle.standardError.write(Data("error: could not read input image \(inputPath)\n".utf8))
    exit(2)
}

let ciImage = CIImage(cgImage: cgImage)
let handler = VNImageRequestHandler(ciImage: ciImage)

let outputCI: CIImage

if strategy == "foreground" {
    // VNGenerateForegroundInstanceMaskRequest — Vision's generic
    // foreground-segmentation model. Output is CROPPED to subject bounds
    // via croppedToInstancesExtent=true.
    let request = VNGenerateForegroundInstanceMaskRequest()
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
    let maskedPixelBuffer: CVPixelBuffer
    do {
        maskedPixelBuffer = try result.generateMaskedImage(
            ofInstances: result.allInstances,
            from: handler,
            croppedToInstancesExtent: true
        )
    } catch {
        FileHandle.standardError.write(Data("error: masked-image generation failed: \(error)\n".utf8))
        exit(2)
    }
    outputCI = CIImage(cvPixelBuffer: maskedPixelBuffer)
} else {
    // VNGeneratePersonSegmentationRequest — person-targeted mask. Output is
    // the FULL input canvas with non-person pixels transparent. We then
    // composite the original image through the mask and crop to the mask's
    // non-transparent bounding box ourselves.
    let request = VNGeneratePersonSegmentationRequest()
    request.qualityLevel = .accurate
    request.outputPixelFormat = kCVPixelFormatType_OneComponent8
    do {
        try handler.perform([request])
    } catch {
        FileHandle.standardError.write(Data("error: Vision request failed: \(error)\n".utf8))
        exit(2)
    }
    guard let result = request.results?.first else {
        FileHandle.standardError.write(Data("warn: no person mask found in \(inputPath)\n".utf8))
        exit(1)
    }
    let maskCI = CIImage(cvPixelBuffer: result.pixelBuffer)
    // Scale the mask to match the input image extent (Vision masks come back
    // at the model's internal resolution, e.g. 2016x1512).
    let scaleX = ciImage.extent.width / maskCI.extent.width
    let scaleY = ciImage.extent.height / maskCI.extent.height
    let scaledMask = maskCI.transformed(by: CGAffineTransform(scaleX: scaleX, y: scaleY))
    let blend = CIFilter.blendWithMask()
    blend.inputImage = ciImage
    blend.maskImage = scaledMask
    blend.backgroundImage = CIImage(color: .clear).cropped(to: ciImage.extent)
    guard let blended = blend.outputImage else {
        FileHandle.standardError.write(Data("error: blend filter produced no output\n".utf8))
        exit(2)
    }
    outputCI = blended.cropped(to: ciImage.extent)
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
