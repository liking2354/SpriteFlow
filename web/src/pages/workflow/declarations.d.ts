declare module "*.jsx" {
  const component: any;
  export default component;
}

declare module "*/components/NodeFlow" {
  const NodeFlow: React.FC<{
    initialNodeSchemas?: any;
    initialWorkflowData?: any;
  }>;
  export default NodeFlow;
}
