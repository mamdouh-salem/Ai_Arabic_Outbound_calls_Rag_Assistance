# scripts/visualization.py
import os
from outbound_ai.graph.deps import GraphDependencies
from outbound_ai.graph.build import build_graph

# Pass None for all 7 required dependencies to safely compile the structure
mock_deps = GraphDependencies(
    stt=None,           # Added this missing dependency
    tts=None,
    endpointing=None,
    kb_retrieve=None,
    intent_classify=None,
    report=None,
    route=None
)

# 2. Compile the graph
app = build_graph(mock_deps)

# 3. Generate and save the PNG
try:
    png_data = app.get_graph().draw_mermaid_png()
    output_path = os.path.join(os.path.dirname(__file__), "../graph_workflow.png")
    
    with open(output_path, "wb") as f:
        f.write(png_data)
    print("Success! Graph visualization saved as graph_workflow.png")
except Exception as e:
    print(f"Could not generate PNG automatically: {e}")
    print("\n--- Copy & paste this Mermaid code into https://mermaid.live instead: ---\n")
    print(app.get_graph().draw_mermaid())
