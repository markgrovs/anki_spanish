try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    Image = None

from pathlib import Path

def create_collage(images: list[Path], out_path: Path, max_cells: int = 4, label_indices=False) -> Path | None:
    """
    Combine list of image paths into a single grid image.
    If label_indices is True, draw "1", "2", "3", "4" overlays on them.
    """
    if Image is None:
        return None
    if not images:
        return None

    imgs = images[:max_cells]
    n = len(imgs)
    if n == 0: return None
    
    # Always force 2x2 grid for consistency if max_cells=4
    cols = 2
    rows = 2
    tile_w, tile_h = 600, 450
    
    W, H = cols * tile_w, rows * tile_h
    canvas = Image.new("RGB", (W, H), (0, 0, 0))
    
    idx = 0
    for r in range(rows):
        for c in range(cols):
            if idx >= n: break
            
            p = imgs[idx]
            try:
                im = Image.open(p).convert("RGB")
                # Center crop to 4:3 aspect ratio to avoid distortion
                im_ratio = im.width / im.height
                tile_ratio = tile_w / tile_h
                
                if im_ratio > tile_ratio:
                    # Too wide, crop width
                    new_w = int(im.height * tile_ratio)
                    offset = (im.width - new_w) // 2
                    im = im.crop((offset, 0, offset + new_w, im.height))
                else:
                    # Too tall, crop height
                    new_h = int(im.width / tile_ratio)
                    offset = (im.height - new_h) // 2
                    im = im.crop((0, offset, im.width, offset + new_h))
                    
                im = im.resize((tile_w, tile_h), Image.Resampling.LANCZOS)
                
                x0 = c * tile_w
                y0 = r * tile_h
                canvas.paste(im, (x0, y0))
                
                if label_indices:
                    draw = ImageDraw.Draw(canvas)
                    # Draw a big number in the corner
                    # We don't have a guaranteed font, so we use default or try a system one
                    # Fallback: draw a black box with white text
                    label = str(idx + 1)
                    # draw box
                    box_s = 60
                    draw.rectangle([x0, y0, x0 + box_s, y0 + box_s], fill=(0,0,0))
                    # draw text - primitive but visible
                    draw.text((x0 + 20, y0 + 15), label, fill=(255,255,255))
                    
            except Exception as e:
                print(f"Error processing image {p}: {e}")
                
            idx += 1
            
    canvas.save(out_path)
    return out_path
