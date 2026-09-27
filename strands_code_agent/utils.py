import base64


def image_to_base64(image_path):
    """Read an image file and return its contents as a base64-encoded string."""
    with open(image_path, 'rb') as f:
            return base64.b64encode(f.read()).decode('utf-8')


def get_response_metrics(
          response,
          price_1M_input_tokens=None,
          price_1M_output_tokens=None,
          model_id=None,
          price_table=None):
    """
    For the latest pricing see: https://aws.amazon.com/bedrock/pricing

    Static-table threading (Phase 5, display only): when explicit prices are
    absent but ``model_id`` plus a ``price_table`` (id-substring to
    ``(in, out)`` USD-per-1M pair, e.g. ``MODEL_PRICING``) are given, prices
    resolve from the table on exact-substring hit; unknown ids simply omit
    ``cost``. The table lives in the CLI layer — this module never imports
    it (layering: the caller passes it in).
    """
    summary = response.metrics.get_summary()
    inputTokens = summary['accumulated_usage']['inputTokens']
    outputTokens = summary['accumulated_usage']['outputTokens']
    metrics = {
        'total_cycles': summary['total_cycles'],
        'total_duration': summary['total_duration'],
        'input_tokens': inputTokens,
        'output_tokens': outputTokens,
    }

    if (not price_1M_input_tokens or not price_1M_output_tokens) and model_id and price_table:
        lowered = str(model_id).lower()
        for key in price_table:
            if key in lowered:
                price_1M_input_tokens = price_table[key][0]
                price_1M_output_tokens = price_table[key][1]
                break

    if price_1M_input_tokens and price_1M_output_tokens:
        metrics['cost'] = (inputTokens * price_1M_input_tokens / 1_000_000) + (outputTokens * price_1M_output_tokens / 1_000_000)

    return metrics
