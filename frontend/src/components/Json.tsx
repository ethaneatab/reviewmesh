export default function Json({ value, testid }: { value: unknown; testid?: string }) {
  return (
    <div className="json" data-testid={testid}>
      <pre>{JSON.stringify(value, null, 2)}</pre>
    </div>
  )
}
