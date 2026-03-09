# Workflow Visualization Component

A beautiful, interactive visualization of the Reflexio data processing workflow using React Flow.

## Overview

This component visualizes how requests flow through the Reflexio system, showing:
- Request entry points
- Sliding window processing
- Extractor fan-out (Profile, Feedback, Success)
- Supabase storage endpoints

## Components

### WorkflowVisualization.tsx
Main component that generates the flow diagram based on configuration.

**Props:**
```typescript
interface WorkflowVisualizationProps {
  config: Config  // Current Reflexio configuration
}
```

**Features:**
- Automatically generates nodes and edges from config
- Live updates when config changes (uses useMemo)
- Interactive zoom, pan, and fit view
- Color-coded edges by extractor type
- Smooth animations on data flow

### Custom Nodes

#### nodes/RequestNode.tsx
- Entry point of the workflow
- Shows "Sessions & Interactions"
- Light blue color scheme

#### nodes/SlidingWindowNode.tsx
- Displays window size and stride from config
- Interactive info tooltip
- Yellow/gold color scheme

#### nodes/ExtractorNode.tsx
- Reusable for all extractor types (profile, feedback, success)
- Click to expand and view configurations
- Shows extractor count badge
- Displays prompt previews (200 char limit)
- Color-coded by type:
  - Purple: Profile extractors
  - Orange: Feedback extractors
  - Green: Success evaluators

#### nodes/StorageNode.tsx
- Terminal node representing database
- Shows storage type (local/s3/supabase)
- Click to expand and view all tables
- Lists 5 database tables with descriptions

## Usage

### Basic Usage

```tsx
import WorkflowVisualization from "@/components/workflow/WorkflowVisualization"

function SettingsPage() {
  const [config, setConfig] = useState<Config>(/* ... */)

  return (
    <WorkflowVisualization config={config} />
  )
}
```

### Integration with Settings

The component is integrated into the Settings page as the third tab:

1. Navigate to: `http://localhost:8080/settings`
2. Click on "Workflow Visualization" tab
3. View and interact with the diagram

### Live Updates

The diagram automatically updates when:
- Extractors are added or removed
- Window size or stride values change
- Storage configuration changes

No manual refresh needed!

## Styling

### Color Palette

Following the project's shadcn color scheme:

```typescript
const colors = {
  background: "#f1faee",
  request: "#a8dadc",
  window: "#ffb703",
  profile: { bg: "#f3e5f5", border: "#9c27b0" },
  feedback: { bg: "#fff3e0", border: "#ff9800" },
  success: { bg: "#e8f5e9", border: "#588157" },
  storage: { bg: "#e8f5e9", border: "#588157" },
  dark: "#1d3557",
  edge: "#457b9d"
}
```

### Customization

To modify node appearance, edit the individual node components in `nodes/`.

To change layout algorithm, modify the position calculations in `WorkflowVisualization.tsx`.

## Interactive Features

### Zoom & Pan
- Use mouse wheel to zoom
- Click and drag to pan
- Use the controls in bottom-left corner

### Node Details
- Click on extractor nodes to expand configuration details
- Click on storage node to view database tables
- Hover over sliding window info icon for explanation

### Edge Animation
- Animated edges show data flow direction
- Color-coded by extractor type
- Arrow markers indicate flow direction

## Dependencies

- `@xyflow/react`: React Flow library for diagrams
- `lucide-react`: Icons
- `react`: React 18+
- `next`: Next.js 16+

## Development

### Adding New Node Types

1. Create new component in `nodes/` directory:
```tsx
import { Handle, Position } from "@xyflow/react"

export function MyCustomNode({ data }) {
  return (
    <div>
      <Handle type="target" position={Position.Top} />
      {/* Your node content */}
      <Handle type="source" position={Position.Bottom} />
    </div>
  )
}
```

2. Register in `WorkflowVisualization.tsx`:
```tsx
const nodeTypes = {
  // ... existing types
  myCustomNode: MyCustomNode,
}
```

3. Add to node generation logic:
```tsx
generatedNodes.push({
  id: "my-node",
  type: "myCustomNode",
  position: { x: 100, y: 100 },
  data: { /* ... */ },
})
```

### Modifying Layout

The layout is calculated in the `useMemo` hook in `WorkflowVisualization.tsx`:

```tsx
const { nodes, edges } = useMemo(() => {
  // Modify position calculations here
  const extractorX = 200
  const extractorSpacing = 300
  // ...
}, [config])
```

## Performance

- Uses `useMemo` to prevent unnecessary re-renders
- Efficient edge/node generation
- Lightweight components (~60kb gzipped with React Flow)

## Browser Support

- Chrome/Edge: ✅
- Firefox: ✅
- Safari: ✅
- Mobile: ✅ (with touch support)

## Troubleshooting

### Diagram Not Rendering
- Check that `@xyflow/react` CSS is imported
- Verify container has defined height (default: 700px)
- Check browser console for errors

### Nodes Overlapping
- Adjust spacing calculations in `WorkflowVisualization.tsx`
- Increase `extractorSpacing` value
- Modify Y position increments

### Tooltips Not Showing
- Ensure Z-index is set correctly
- Check that parent containers don't have `overflow: hidden`
- Verify click handlers are not blocked

## Future Enhancements

Potential improvements:
- Export diagram as PNG/SVG
- Dark mode support
- Drag-and-drop to reorder extractors
- Real-time data flow indicators
- Performance metrics overlay
- Custom edge labels
- Collapsible node groups

## License

Part of the Reflexio project.
