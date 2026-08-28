# Notes


### Aug 10 2026

* Needed a custom PCB footprint in KiCad
  * took the case design I had in Fusion360 and created a new "PCB Mask" sketch. Projected the faceplate border to the mask layer and created the pcb outline with a -5mm offset. Projected the old LED surface mount holes and the slide pot cutouts so I'd be able to place the components perfectly.
  * right click on the PCB Mask sketch, export as DXF. You can leave the "Projected Geometry" box ticked, we'll just need to delete some of these alignment features later.
  * It might end up being easier to just overlay new features over the projected features (new circles for LED placement over the projected ones) and disable the projected geometry box. Try this out if you're running into trouble.
* In KiCad PCB Editor
  * File -> Import -> Graphics, pick the "PCB Mask.dxf" file, import it to the Edge Cuts layer.
  * It gets imported as one "group" of lines so get things lined up decently first and then we can ungroup and remove alignment features. 
    * right click on the outline -> Grouping -> Ungroup
    * now we can delete alignment features once the schematic is placed appropriately 