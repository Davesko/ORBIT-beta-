import AppKit
let folder=CommandLine.arguments[1]
let sizes=[16,32,64,128,256,512,1024]
for size in sizes {
 let image=NSImage(size:NSSize(width:size,height:size))
 image.lockFocus();let s=CGFloat(size)
 NSColor(calibratedRed:0.075,green:0.13,blue:0.13,alpha:1).setFill()
 NSBezierPath(roundedRect:NSRect(x:0,y:0,width:s,height:s),xRadius:s*0.22,yRadius:s*0.22).fill()
 let transform=NSAffineTransform();transform.translateX(by:s/2,yBy:s/2);transform.rotate(byDegrees:30);transform.concat()
 let lime=NSColor(calibratedRed:0.85,green:0.97,blue:0.52,alpha:1)
 lime.setStroke();let p=NSBezierPath(ovalIn:NSRect(x:-s*0.34,y:-s*0.16,width:s*0.68,height:s*0.32));p.lineWidth=s*0.045;p.stroke()
 let p2=NSBezierPath(ovalIn:NSRect(x:-s*0.16,y:-s*0.34,width:s*0.32,height:s*0.68));p2.lineWidth=s*0.045;p2.stroke()
 lime.setFill();NSBezierPath(ovalIn:NSRect(x:-s*0.07,y:-s*0.07,width:s*0.14,height:s*0.14)).fill()
 NSColor(calibratedRed:0.95,green:0.98,blue:0.86,alpha:1).setFill();NSBezierPath(ovalIn:NSRect(x:s*0.235,y:s*0.085,width:s*0.085,height:s*0.085)).fill()
 image.unlockFocus()
 let rep=NSBitmapImageRep(data:image.tiffRepresentation!)!;let png=rep.representation(using:.png,properties:[:])!
 let url=URL(fileURLWithPath:folder).appendingPathComponent("orbit-\(size).png");try png.write(to:url)
}
