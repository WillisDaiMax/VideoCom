// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "VideoCom",
    platforms: [.macOS(.v14)],
    targets: [
        .executableTarget(name: "VideoCom", path: "Sources/VideoCom")
    ]
)
